"""Preserve native logs across selection, failed changes, reboot and rollback."""

from contextlib import ExitStack, nullcontext
import functools
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading

from guest import boot


SYSTEM = "/usr/local/nix/state/gcroots/system"
INVALID = {
    "invalidEnable": "enable", "invalidFiles": "files", "invalidName": "files",
    "emptyName": "files", "optionName": "files", "invalidFile": "files",
    "invalidMode": "files", "numericMode": "files", "readOnlyMode": "files",
    "disabledFiles": "files",
}


def root(guest, suffix=""):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"cat {SYSTEM}{suffix}"))
    if len(paths) != 1:
        raise RuntimeError(f"missing system root: {paths}")
    return paths[0]


def reject(guest, command, reason):
    result = guest.command(command + "; echo LOGGING-ERROR:$status")
    if not re.search(r"(?m)^LOGGING-ERROR:.+", result) or reason not in result:
        raise RuntimeError(f"operation did not reject {reason}: {result}")
    guest.command("test ! -e '#s/nix9-system'")


def mode(guest, name, permissions):
    guest.command(f"test -A /sys/log/{name}")
    expected = "a-" + stat.filemode(int(permissions, 8))[1:]
    guest.command(f"ls -ld /sys/log/{name} | awk '{{print $1}}'", expected)


def events(guest, expected):
    output = guest.command("cat /sys/log/nix9")
    records = re.findall(r"(?m)^nix9-logs .{15} nix9 (boot|switch|rollback) (/usr/local/nix/store/[^\s]+)$", output)
    if records != expected:
        raise RuntimeError(f"unexpected generation events: {records}; expected {expected}")


def refresh(guest):
    guest.command("for(i in 1 2 3) . /usr/local/pkg/nix9/system")
    guest.command("@{ home=/tmp/logging-login; rc -el -c 'echo LOGGING-READY' }", "LOGGING-LOGIN")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_LOGGING_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "logging.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("logging.nix"), work / "logging.nix")
    (work / "terminal-profile.rc").write_text("prompt=('term% ' '\t')\nexec rc -i\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    server = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join)
    stack.callback(server.shutdown)
    base = f"http://10.0.2.2:{server.server_port}"
    expected = []
    with boot(qemu, disk, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        for name in ("logging.nix", "terminal-profile.rc"):
            guest.command(f"hget -o /tmp/{name} {base}/{name}")
        for name in ("one", "two", "disabled", "conflict", "exclusive", "temporary", *INVALID):
            guest.command(f"echo '(import ./logging.nix).{name}' > /tmp/{name}.nix")
        guest.command("test ! -e /sys/log/nix9 && test ! -e /sys/log/nix9-new")
        guest.command("echo retained > /sys/log/nix9-test; chmod 666 /sys/log/nix9-test")
        guest.command("echo manual > /sys/log/nix9-manual; chmod 600 /sys/log/nix9-manual")
        guest.command("mkdir /sys/log/nix9-directory")
        guest.command("echo exclusive > /sys/log/nix9-exclusive; chmod +l /sys/log/nix9-exclusive")
        guest.command("echo temporary > /sys/log/nix9-temporary; chmod +t /sys/log/nix9-temporary")
        guest.command("nix9-rebuild build /tmp/one.nix")
        one = root(guest, "-build")
        guest.command("test ! -e /sys/log/nix9 && test ! -e /sys/log/nix9-new")
        for name in ("conflict", "exclusive", "temporary"):
            reject(guest, f"nix9-rebuild switch /tmp/{name}.nix", "not a regular log file")
            guest.command(f"test ! -e {SYSTEM}")
            guest.command("test ! -e /sys/log/nix9 && test ! -e /sys/log/nix9-should-not-exist")
        for name, reason in INVALID.items():
            reject(guest, f"nix9-rebuild switch /tmp/{name}.nix", "logging." + reason)
            guest.command(f"test ! -e {SYSTEM}")
        guest.command("nix9-rebuild switch /tmp/one.nix")
        if root(guest) != one:
            raise RuntimeError("switch did not reuse the built logging generation")
        expected.append(("switch", one))
        events(guest, expected)
        mode(guest, "nix9", "0640")
        mode(guest, "nix9-test", "0600")
        mode(guest, "nix9-new", "0640")
        guest.command("cat /sys/log/nix9-test", "retained")
        guest.command("echo previous-generation > /sys/log/nix9-new")
        guest.command("mkdir -p /tmp/logging-login/lib")
        guest.command("echo 'echo LOGGING-LOGIN' > /tmp/logging-login/lib/profile")
        # Session activation neither prepares machine-wide modes nor writes events.
        guest.command("chmod 400 /sys/log/nix9-test")
        refresh(guest)
        mode(guest, "nix9-test", "0400")
        events(guest, expected)
        guest.command("nix9-rebuild switch /tmp/two.nix")
        two = root(guest)
        expected.append(("switch", two))
        events(guest, expected)
        mode(guest, "nix9", "0600")
        mode(guest, "nix9-test", "0644")
        guest.command("cat /sys/log/nix9-test", "retained")
        guest.command("cat /sys/log/nix9-new", "previous-generation")
        guest.command("cp /sys/log/nix9 /tmp/before-rejected-selection")
        guest.command("@{ status='' } > '#s/nix9-profile'")
        reject(guest, "nix9-rebuild switch /tmp/one.nix", "profiles are locked")
        if root(guest) != two:
            raise RuntimeError("failed selection changed the system")
        guest.command("rm '#s/nix9-profile'; cmp /sys/log/nix9 /tmp/before-rejected-selection")
        guest.command("nix9-rebuild rollback")
        if root(guest) != one:
            raise RuntimeError("rollback did not restore the first logging generation")
        expected.append(("rollback", one))
        events(guest, expected)
        mode(guest, "nix9", "0640")
        mode(guest, "nix9-test", "0600")
        guest.command("nix9-rebuild switch /tmp/two.nix")
        expected.append(("switch", two))
        guest.command("chmod 666 /sys/log/nix9-test; rm /sys/log/nix9-added")
        guest.command("cp /tmp/terminal-profile.rc /usr/glenda/lib/profile")
        print("PASS: safe preparation, append mode, preserved contents, event records and rejected changes", flush=True)
    options = dict(snapshot=False, configure_network=False)
    with boot(qemu, disk, **options) as guest:
        guest.command(f"cat {SYSTEM}-boot", two)
        expected.append(("boot", two))
        events(guest, expected)
        mode(guest, "nix9-test", "0644")
        mode(guest, "nix9-added", "0640")
        guest.command("cat /sys/log/nix9-test", "retained")
        guest.command("echo retained-after-rollback > /sys/log/nix9-added")
        refresh(guest)
        events(guest, expected)
        guest.command("nix9-rebuild rollback")
        expected.append(("rollback", one))
        events(guest, expected)
        print("PASS: reboot restores file modes, recreates missing logs and preserves history", flush=True)
    with boot(qemu, disk, **options) as guest:
        guest.command(f"cat {SYSTEM}-boot", one)
        expected.append(("boot", one))
        events(guest, expected)
        mode(guest, "nix9", "0640")
        mode(guest, "nix9-test", "0600")
        guest.command("cat /sys/log/nix9-added", "retained-after-rollback")
        guest.command("cat /sys/log/nix9-manual", "manual")
        guest.command("ls -ld /sys/log/nix9-manual | awk '{print $1}'", "--rw-------")
        guest.command("nix9-rebuild switch /tmp/disabled.nix")
        disabled = root(guest)
        expected.append(("switch", disabled))
        events(guest, expected)
        refresh(guest)
        events(guest, expected)
        guest.command("cp /sys/log/nix9 /tmp/logging-disabled-history")
        print("PASS: rollback restores policy without rolling back log data", flush=True)
    with boot(qemu, disk, **options) as guest:
        guest.command(f"cat {SYSTEM}-boot", disabled)
        guest.command("test ! -f $nix9System/logging && test ! -f $nix9System/log-event")
        guest.command("cmp /sys/log/nix9 /tmp/logging-disabled-history")
        guest.command("cat /sys/log/nix9-test", "retained")
        events(guest, expected)
        print("PASS: disabling logging preserves files and stops generation events", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "firstSystem": one, "secondSystem": two,
        "unmanagedSystem": disabled, "events": expected, "configuredBoots": 3,
        "rejectedConfigurations": list(INVALID),
        "checks": ["nontruncating-preparation", "append-mode", "declared-permissions",
                   "boot-and-selection-events", "failed-selection-no-success-event",
                   "invalid-file-types", "preflight-no-log-mutations", "session-no-mutations",
                   "boot-recreation", "unmanaged-files-preserved", "rollback", "disable"],
    }, indent=2) + "\n")
