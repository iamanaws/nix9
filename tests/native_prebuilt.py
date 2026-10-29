"""Transfer built systems to a second machine, check, select, reboot and roll back."""

from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from artifacts import ArtifactServer
from guest import boot


ROOTS = "/usr/local/nix/state/gcroots"
ROOT = ROOTS + "/machines/target/system"
HOOKS = ("/rc/bin/termrc.local", "/rc/bin/cpurc.local", "/rc/lib/rcmain.local")
NIX_CONFIG = "substituters =\nmax-jobs = 0\nbuilders ="


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def disable_builds(guest):
    guest.command("ifs=() { NIX_CONFIG=`{echo 'substituters ='; echo 'max-jobs = 0'; echo 'builders ='} }")
    settings = guest.command("echo $NIX_CONFIG").splitlines()
    if any(setting not in settings for setting in NIX_CONFIG.splitlines()):
        raise RuntimeError("receiver build and substitution settings were not applied")


def store_path(guest, root):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat " + root))
    if len(paths) != 1:
        raise RuntimeError(f"missing store root: {root}")
    return paths[0]


def rejected(guest, command, reason=None):
    result = guest.command("rc -c " + quote(command) + "; echo PREBUILT-ERROR:$status")
    if (not re.search(r"(?m)^PREBUILT-ERROR:.+", result) or "syntax error" in result
            or (reason and reason not in result)):
        raise RuntimeError(f"operation was not rejected: {command}: {result}")
    return result


def clean(guest):
    guest.command("test ! -e '#s/nix9-system-target'")
    guest.command("for(file in " + ROOT + "-candidate-*) test ! -e $file")


def snapshot(guest):
    return {command: guest.command(command) for command in (
        "cat " + ROOT, "nix9-rebuild list", "echo `{cat /dev/sysname}", "cat /sys/log/nix9")}


def unchanged(guest, previous):
    if snapshot(guest) != previous:
        raise RuntimeError("a check or rejected selection changed the system, history, hostname or events")
    clean(guest)


def current(guest, version, path):
    guest.command("cat " + ROOT, path)
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("prebuilt-version", version)
    guest.command("cat /cfg/nix9/files/version", version)
    guest.command("echo `{cat /dev/sysname}", "target-" + version)
    guest.command("cat /usr/glenda/prebuilt-user-data", "persistent-user-data")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_PREBUILT_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("prebuilt.nix"), work / "prebuilt.nix")
    disks = {}
    for name in ("builder", "target"):
        disk = work / (name + ".qcow2")
        if disk.exists():
            raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                        "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
        disks[name] = disk

    with ArtifactServer(work, work / "closure.export") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://10.0.2.2:{server.server_port}"
            with boot(qemu, disks["builder"], snapshot=False) as builder:
                builder.child.timeout = 900
                builder.command(f"cd / && hget {base}/bootstrap.tar | tar x")
                builder.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init builder")
                builder.command(f"hget -o /tmp/prebuilt.nix {base}/prebuilt.nix")
                builder.command("nix-build /tmp/prebuilt.nix -A bundle --out-link " + ROOTS + "/prebuilt-fixtures")
                bundle = store_path(builder, ROOTS + "/prebuilt-fixtures")
                paths = {name: store_path(builder, bundle + "/" + name) for name in (
                    "one", "two", "wrong", "data", "notSystem", "unsupported",
                    "incomplete", "failedActivation", "needsRuntime")}
                builder.command("nix9-rebuild select " + paths["wrong"])
                builder.command(". /usr/local/pkg/nix9/system")
                rejected(builder, "nix9-rebuild select " + paths["one"], "another machine")
                builder.command("cat $nix9SystemRoot", paths["wrong"])
                builder.command("nix-store --export `{nix-store -qR " + bundle + "} > /tmp/closure.export")
                builder.command("size=`{ls -l /tmp/closure.export | awk '{print $6}'}")
                builder.command("hget -r 'Content-Length: '^$size -P " + base + "/closure.export < /tmp/closure.export")
                if not server.received.is_set():
                    raise RuntimeError("builder did not upload the system closures")
            data = (work / "closure.export").read_bytes()
            (work / "truncated.export").write_bytes(data[:64])

            with boot(qemu, disks["target"], snapshot=False) as guest:
                guest.child.timeout = 900
                guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
                guest.command(". /usr/local/pkg/nix9/activate")
                for action in ("check", "select"):
                    rejected(guest, f"nix9-rebuild {action} {paths['one']}", "initialize this machine")
                guest.command("nix9-rebuild init target")
                disable_builds(guest)
                guest.command("test ! -e /tmp/prebuilt.nix")
                for action in ("check", "select"):
                    rejected(guest, "nix9-rebuild " + action, "expected a system store path")
                    rejected(guest, f"nix9-rebuild {action} /tmp/outside", "canonical system store path")
                    rejected(guest, f"nix9-rebuild {action} {paths['one']}/files", "canonical system store path")
                    rejected(guest, f"nix9-rebuild {action} {paths['one']}", "not registered locally")
                guest.command(f"hget -o /tmp/truncated.export {base}/truncated.export")
                rejected(guest, "nix-store --import < /tmp/truncated.export")
                for action in ("check", "select"):
                    rejected(guest, f"nix9-rebuild {action} {paths['one']}", "not registered locally")
                guest.command("test ! -e " + ROOT)
                guest.command("test ! -d " + ROOT + ".generations")
                clean(guest)

                guest.command(f"hget -o /tmp/closure.export {base}/closure.export")
                guest.command("nix-store --import < /tmp/closure.export")
                guest.command("nix-store --realise " + bundle + " --add-root " + ROOTS + "/prebuilt-fixtures")
                guest.command("deriver=`{nix-store -qd " + paths["two"] + "}; test ! -e $deriver")
                for index, hook in enumerate(HOOKS):
                    guest.command("echo '# prebuilt hook fixture' >> " + hook)
                    guest.command(f"cp {hook} /tmp/original-hook-{index}")
                guest.command("nix9-rebuild check " + paths["one"], "System check passed: " + paths["one"])
                guest.command("test ! -e " + ROOT + " && test ! -d " + ROOT + ".generations")
                guest.command("test ! -e /sys/log/prebuilt && test ! -e /usr/local/pkg/nix9/system")
                for index, hook in enumerate(HOOKS):
                    guest.command(f"cmp {hook} /tmp/original-hook-{index} && test ! -e {hook}.nix9-original")
                clean(guest)
                guest.command("echo persistent-user-data > /usr/glenda/prebuilt-user-data")
                guest.command("nix9-rebuild select " + paths["one"])
                current(guest, "one", paths["one"])
                history = guest.command("nix9-rebuild list")
                guest.command("nix9-rebuild select " + paths["one"])
                if guest.command("nix9-rebuild list") != history:
                    raise RuntimeError("repeated selection created a duplicate generation")
                before = snapshot(guest)
                guest.command("nix9-rebuild check " + paths["two"])
                unchanged(guest, before)
                guest.command("ls -ld /sys/log/prebuilt | awk '{print $1}'", "a-rw-r-----")
                for name, reason in (
                    ("wrong", "another machine"), ("notSystem", "expected a built nix9 system"),
                    ("unsupported", "unsupported system format"), ("incomplete", "incomplete system"),
                    ("failedActivation", "activation check failed"), ("needsRuntime", "activation check failed"),
                ):
                    for action in ("check", "select"):
                        rejected(guest, f"nix9-rebuild {action} {paths[name]}", reason)
                        unchanged(guest, before)
                guest.command("echo -n > /tmp/prebuilt-site.ndb")
                guest.command("nix9-rebuild check " + paths["needsRuntime"])
                unchanged(guest, before)
                guest.command("rm /tmp/prebuilt-site.ndb")

                guest.command("mv " + paths["data"] + " /tmp/prebuilt-saved-data")
                for action in ("check", "select"):
                    rejected(guest, f"nix9-rebuild {action} {paths['two']}", "closure verification failed")
                    unchanged(guest, before)
                guest.command("mv /tmp/prebuilt-saved-data " + paths["data"])
                guest.command("cp " + paths["data"] + " /tmp/prebuilt-saved-data")
                guest.command("chmod u+w " + paths["data"] + "; echo changed > " + paths["data"])
                for action in ("check", "select"):
                    rejected(guest, f"nix9-rebuild {action} {paths['two']}", "closure verification failed")
                    unchanged(guest, before)
                guest.command("cp /tmp/prebuilt-saved-data " + paths["data"])
                guest.command("nix-store --verify-path " + paths["data"])
                guest.command("cp /rc/bin/termrc.local /tmp/managed-hook")
                guest.command("echo '# edited hook' >> /rc/bin/termrc.local")
                for action in ("check", "select"):
                    rejected(guest, f"nix9-rebuild {action} {paths['two']}", "startup hook was edited")
                    unchanged(guest, before)
                guest.command("cp /tmp/managed-hook /rc/bin/termrc.local")
                guest.command("@{ status='' } > '#s/nix9-system-target'")
                for action in ("check", "select"):
                    rejected(guest, f"nix9-rebuild {action} {paths['two']}", "system changes are locked")
                    guest.command("test -e '#s/nix9-system-target'")
                guest.command("rm '#s/nix9-system-target'")
                guest.command("@{ status='' } > '#s/nix9-profile'")
                rejected(guest, "nix9-rebuild select " + paths["two"], "profiles are locked")
                guest.command("rm '#s/nix9-profile'")
                unchanged(guest, before)

                guest.command("nix9-rebuild select " + paths["two"])
                guest.command("prebuilt-version", "one")
                current(guest, "two", paths["two"])
                guest.command("ls -ld /sys/log/prebuilt | awk '{print $1}'", "a-rw-------")
                guest.command("rm " + ROOTS + "/prebuilt-fixtures; nix-store --gc")
                guest.command("nix-store --verify-path " + paths["one"] + " " + paths["two"])
                clean(guest)
                print("PASS: transfer, check without selection, local closure validation, rejected changes and generation reuse", flush=True)
        finally:
            server.shutdown()
            thread.join()

    # The fixture server and configuration source are unavailable on later boots.
    for version in ("two", "one"):
        with boot(qemu, disks["target"], snapshot=False, configure_network=False,
                  prompt=r"(?m)^(?:term)?% ") as guest:
            guest.child.timeout = 600
            guest.command(". /usr/local/pkg/nix9/activate")
            disable_builds(guest)
            current(guest, version, paths[version])
            guest.command("cat " + ROOT + "-boot", paths[version])
            if version == "two":
                guest.command("nix9-rebuild rollback")
                current(guest, "one", paths["one"])
                rejected(guest, "nix9-rebuild delete 2", "booted generation")
                guest.command("nix-store --gc")
                guest.command("nix-store --verify-path " + paths["two"])
            else:
                guest.command("nix9-rebuild delete 2; nix-store --gc")
                guest.command("test ! -e " + paths["two"])
                guest.command("nix9-rebuild check " + paths["one"])
                records = guest.command("cat /sys/log/nix9")
                actions = re.findall(r"(?m)^target-(?:one|two) .{15} nix9 (switch|boot|rollback) (\S+)$", records)
                expected = [("switch", paths["one"]), ("switch", paths["one"]),
                            ("switch", paths["two"]), ("boot", paths["two"]),
                            ("rollback", paths["one"]), ("boot", paths["one"])]
                if actions != expected:
                    raise RuntimeError(f"unexpected selection events: {actions}")
            clean(guest)
    print("PASS: imported generations survive reboot, preserve user data and protect the booted closure through rollback and GC", flush=True)

destination = Path(output)
destination.mkdir(parents=True, exist_ok=True)
(destination / "results.json").write_text(json.dumps({
    "status": "passed", "machines": 2, "targetReboots": 2,
    "systems": {name: paths[name] for name in ("one", "two")},
    "checks": ["installation-closures", "trusted-export-import", "truncated-transfer",
               "no-target-evaluation-or-build", "check-without-selection", "full-closure-integrity",
               "wrong-machine", "runtime-prerequisites", "startup-hook-conflicts", "locks",
               "failed-selection-rollback", "generation-reuse", "selection-events", "session-refresh",
               "offline-reboot", "rollback", "boot-root-and-history-gc", "persistent-user-data"],
}, indent=2) + "\n")
