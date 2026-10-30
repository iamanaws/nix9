"""Exercise ordered native directory bindings through system generations."""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from guest import boot, files_guest


DATA = "/usr/glenda/nix9-bind"
ROOT = "/usr/local/nix/state/gcroots/machines/test/system"


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def rejected(guest, command, reason):
    result = guest.command("rc -c " + quote(command) + "; echo BINDING-ERROR:$status")
    if not re.search(r"(?m)^BINDING-ERROR:.+", result) or reason not in result or "syntax error" in result:
        raise RuntimeError(f"operation did not reject {reason}: {result}")
    return result


qemu, image, archive, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    disk = Path(directory) / "bindings.qcow2"
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    files = {name: Path(__file__).with_name(name) for name in
             ("bindings.nix", "binding-checks.nix", "binding-helper.rc", "binding-failed-refresh.rc")}
    files["bootstrap.tar"] = archive
    with files_guest(qemu, disk, files, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init test")
        guest.command("nix-instantiate --eval --strict --json /tmp/binding-checks.nix")
        for name in ("one", "two", "removed", "unavailable", "optional", "chain", "merged"):
            guest.command(f"echo '(import ./bindings.nix {{}}).{name}' > /tmp/{name}.nix")
        guest.command("nix9-rebuild build /tmp/one.nix")
        guest.command("candidate=`{cat " + ROOT + "-build}; nix9-rebuild check $candidate")
        guest.command("test ! -e " + DATA + "-view")
        guest.command("nix9-rebuild select $candidate")
        guest.command("echo original > " + DATA + "-view/original")
        for name in ("one", "two"):
            guest.command(f"echo {name} > {DATA}-{name}/collision; echo {name} > {DATA}-{name}/{name}")
        guest.command(". /usr/local/pkg/nix9/system")
        guest.command("cat " + DATA + "-view/collision", "one")
        guest.command("test -f " + DATA + "-view/two && test ! -e " + DATA + "-view/original")
        guest.command("echo first > " + DATA + "-view/first; test -f " + DATA + "-one/first")
        guest.command(DATA + "-package/binding-command", "package-binding")
        before = guest.command("echo $nix9NamespaceBinds")
        guest.command(". /usr/local/pkg/nix9/system")
        if guest.command("echo $nix9NamespaceBinds") != before:
            raise RuntimeError("unchanged activation replaced bindings")
        guest.command("@{ rfork e; while(! test -e /tmp/check-old) sleep 0.05; "
                      "cat " + DATA + "-view/collision > /tmp/old-result } &")
        guest.command("oldsession=$apid; nix9-rebuild switch /tmp/two.nix")
        # Directory metadata applies to the underlying target, not a shared source.
        guest.command("ls -ld " + DATA + "-one | awk '{print $1}'", "d-rwxr-x---")
        guest.command(". /usr/local/pkg/nix9/system")
        guest.command("cat " + DATA + "-view/collision", "two")
        guest.command("echo second > " + DATA + "-view/second; test -f " + DATA + "-two/second")
        guest.command("test -f " + DATA + "-view/original && test ! -e " + DATA + "-package/binding-command")
        guest.command("echo check > /tmp/check-old; wait $oldsession; cat /tmp/old-result", "one")
        guest.command("nix9-rebuild rollback; . /usr/local/pkg/nix9/system")
        guest.command("cat " + DATA + "-view/collision", "one")
        for change in ("bind -a " + DATA + "-two " + DATA + "-view",
                       "bind " + DATA + "-two $nix9NamespaceBinds(4)"):
            rejected(guest, "@{ rfork n; " + change + "; . /usr/local/pkg/nix9/system }",
                     "managed binding was changed")
        guest.command("nix9-rebuild switch /tmp/unavailable.nix")
        failed = rejected(guest, "rc /tmp/binding-failed-refresh.rc", "required binding source is unavailable")
        if "STAGED-NAMESPACE-CLEANED\n" not in failed:
            raise RuntimeError("failed binding staging leaked anchors")
        guest.command("cat " + DATA + "-view/collision", "one")
        guest.command("nix9-rebuild switch /tmp/optional.nix; . /usr/local/pkg/nix9/system")
        guest.command("test -f " + DATA + "-view/original; ~ $#nix9NamespaceBinds 0")
        guest.command("mkdir " + DATA + "-missing; echo recovered > " + DATA + "-missing/recovered")
        guest.command(". /usr/local/pkg/nix9/system")
        guest.command("cat " + DATA + "-view/recovered", "recovered")
        guest.command("nix9-rebuild switch /tmp/chain.nix; . /usr/local/pkg/nix9/system")
        guest.command("cat " + DATA + "-other/collision", "one")
        guest.command("nix9-rebuild switch /tmp/merged.nix; . /usr/local/pkg/nix9/system")
        guest.command("cat " + DATA + "-view/collision", "two")
        guest.command("nix9-rebuild switch /tmp/one.nix; . /usr/local/pkg/nix9/system")
        guest.command("nix-store --gc")
        guest.command(DATA + "-package/binding-command", "package-binding")
        guest.command("@{ rfork e; . $nix9NamespaceSystem/namespace/config; "
                      "rc -e /tmp/binding-helper.rc $nix9NamespaceTools/bin/nix9-bindings }", "BINDING-HELPER-PASSED")
        print("PASS: list order, native creation routing, private refresh, rollback, source recovery, conflicts and GC", flush=True)
    with boot(qemu, disk, snapshot=False, configure_network=False, prompt=r"(?m)^(?:term)?% ") as guest:
        guest.child.timeout = 600
        guest.command(". /usr/local/pkg/nix9/system")
        guest.command("cat " + DATA + "-view/collision", "one")
        guest.command(DATA + "-package/binding-command", "package-binding")
        guest.command("nix9-rebuild switch /tmp/removed.nix; . /usr/local/pkg/nix9/system")
        guest.command("cat " + DATA + "-view/original", "original")
        guest.command("~ $#nix9NamespaceBinds 0; test ! -e " + DATA + "-package/binding-command")
        print("PASS: native boot, login and removal restore underlying directories", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "boots": 2,
        "checks": ["native-evaluation", "selection-preflight", "replace-prepend-append", "creation-routing",
                   "module-list-order", "reuse", "private-session", "rollback", "underlying-metadata",
                   "required-failure", "optional-retry", "chained-sources", "manual-conflicts",
                   "hidden-union-change", "anchor-change", "staging-cleanup", "package-source-gc", "boot", "remove"],
    }, indent=2) + "\n")
