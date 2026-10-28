"""Switch machine configurations, preserve startup hooks and reboot offline."""

import contextlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from guest import boot, files_guest


ROOTS = "/usr/local/nix/state/gcroots"
SYSTEM = ROOTS + "/system"
PIN_A = "a" * 64
PIN_C = "c" * 64
REVOCATION = "x509 sha256=" + "d" * 64


def rooted(guest, root=SYSTEM):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"cat {root}"))
    if len(paths) != 1:
        raise RuntimeError(f"missing system root: {paths}")
    return paths[0]


def rejected(guest, command, reason):
    result = guest.command(command + "; echo SYSTEM-ERROR:$status")
    if not re.search(r"(?m)^SYSTEM-ERROR:.+", result) or reason not in result:
        raise RuntimeError(f"system operation was not rejected for {reason}: {result}")


def selected(guest, version, target):
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("echo $nix9System", target)
    guest.command("echo `{cat /dev/sysname}", "nix9" if version == "one" else "nix9-two")
    guest.command("nix9-system-choice", version)
    guest.command(f"nix9-{version}-only", version)
    other = "two" if version == "one" else "one"
    guest.command(f"test ! -e /bin/nix9-{other}-only")
    guest.command("cat /cfg/nix9/files/message", version + "'s configuration")
    guest.command("cat /sys/lib/tls/webfs/revoked", REVOCATION)
    guest.command("cat /sys/lib/tls/webfs/hosts/manual.invalid", "x509 sha256=" + PIN_C)
    guest.command("cat /sys/lib/tls/webfs/hosts/example.invalid", "x509 sha256=" + (PIN_A if version == "one" else PIN_C))
    if version == "two":
        guest.command("test ! -e /cfg/nix9/files/old && test ! -e /cfg/nix9/files/nested")
    else:
        guest.command("cat `{cat /cfg/nix9/files/nested/data}", "retained")
        guest.command("test ! -e /sys/lib/tls/webfs/hosts/second.invalid")


def login(guest, version, target):
    command = "nix9-system-choice; cat /cfg/nix9/files/message; echo $nix9System"
    result = guest.command(f"@{{ home=/tmp/system-login; rc -el -c '{command}' }}", target)
    for expected in ("ORIGINAL-LOGIN-HOOK", version, version + "'s configuration"):
        if expected not in result.splitlines():
            raise RuntimeError(f"login missed {expected}: {result}")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_SYSTEM_TEST_STATE")
with (contextlib.nullcontext(state) if state else tempfile.TemporaryDirectory()) as directory:
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "system.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    fixtures = {"bootstrap.tar": archive, "systems.nix": Path(__file__).with_name("systems.nix")}
    with files_guest(qemu, disk, fixtures, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("echo 'echo terminal > /tmp/nix9-terminal-hook' >> /rc/bin/termrc.local")
        guest.command("echo 'echo ORIGINAL-LOGIN-HOOK' >> /rc/lib/rcmain.local")
        guest.command("cp /rc/bin/termrc.local /tmp/original-terminal; cp /rc/lib/rcmain.local /tmp/original-login")
        guest.command("mkdir -p /tmp/system-login")
        guest.command("mkdir -p /sys/lib/tls/webfs/hosts")
        guest.command("if(test -e /sys/lib/tls/webfs/revoked) rm /sys/lib/tls/webfs/revoked; status=''")
        for host in ("manual.invalid", "example.invalid"):
            guest.command(f"echo 'x509 sha256={PIN_C}' > /sys/lib/tls/webfs/hosts/{host}")
        for name in ("one", "two", "invalidHost", "invalidFile", "conflictingFiles", "invalidPin", "invalidPinHost", "collision", "failedActivation", "notSystem"):
            guest.command(f"echo '(import ./systems.nix).{name}' > /tmp/{name}.nix")
        original_name = guest.command("echo `{cat /dev/sysname}").splitlines()[-1]
        guest.command("nix9-rebuild build /tmp/one.nix")
        first = rooted(guest, ROOTS + "/system-build")
        guest.command("echo `{cat /dev/sysname}", original_name)
        guest.command(f"test ! -e {SYSTEM}")
        # A bad activation target must not select a system or replace local hooks.
        guest.command("echo conflict > /cfg/nix9")
        rejected(guest, "nix9-rebuild switch /tmp/one.nix", "activation check failed")
        guest.command(f"test ! -e {SYSTEM}")
        guest.command("cmp /rc/bin/termrc.local /tmp/original-terminal")
        guest.command("rm /cfg/nix9")
        guest.command("mkdir /cfg/nix9")
        guest.command("echo 'echo device-setup > /tmp/nix9-native-termrc' > /cfg/nix9/termrc")
        guest.command("nix9-rebuild switch /tmp/one.nix")
        if rooted(guest) != first:
            raise RuntimeError("switch did not select the built system")
        guest.command("test -f /sys/lib/tls/webfs/revoked && test ! -s /sys/lib/tls/webfs/revoked")
        guest.command(f"echo '{REVOCATION}' > /sys/lib/tls/webfs/revoked")
        selected(guest, "one", first)
        guest.command("cmp /rc/bin/termrc.local.nix9-original /tmp/original-terminal")
        guest.command("cmp /rc/lib/rcmain.local.nix9-original /tmp/original-login")
        guest.command("nix9-rebuild switch /tmp/two.nix")
        second = rooted(guest)
        selected(guest, "two", second)
        for name, reason in (
            ("invalidHost", "hostName"), ("invalidFile", "files"),
            ("conflictingFiles", "files"), ("invalidPin", "certificatePins"),
            ("invalidPinHost", "certificatePins"), ("collision", "command collision"),
            ("failedActivation", "activation check failed"),
            ("notSystem", "expected a built nix9 system"),
        ):
            rejected(guest, f"nix9-rebuild switch /tmp/{name}.nix", reason)
            if rooted(guest) != second:
                raise RuntimeError("rejected update changed the selected system")
            guest.command("echo `{cat /dev/sysname}", "nix9-two")
            guest.command("nix9-system-choice", "two")
            guest.command("cat /cfg/nix9/files/message", "two's configuration")
            guest.command("test ! -e '#s/nix9-system'")
        guest.command("cp /rc/bin/termrc.local /tmp/managed-terminal")
        guest.command("echo '# manual edit' >> /rc/bin/termrc.local")
        rejected(guest, "nix9-rebuild switch /tmp/one.nix", "startup hook was edited")
        guest.command("cp /tmp/managed-terminal /rc/bin/termrc.local")
        guest.command("rm /rc/bin/termrc.local")
        rejected(guest, "nix9-rebuild switch /tmp/one.nix", "startup hook was removed")
        guest.command("cp /tmp/managed-terminal /rc/bin/termrc.local")
        # A selection failure after the hostname write must restore both settings.
        guest.command("@{ status='' } > '#s/nix9-profile'")
        rejected(guest, "nix9-rebuild switch /tmp/one.nix", "profiles are locked")
        if rooted(guest) != second:
            raise RuntimeError("selection failure did not restore the system root")
        guest.command("echo `{cat /dev/sysname}", "nix9-two")
        guest.command("test ! -e '#s/nix9-system'; rm '#s/nix9-profile'")
        guest.command("@{ status='' } > '#s/nix9-system'")
        rejected(guest, "nix9-rebuild list", "system changes are locked")
        guest.command("test -e '#s/nix9-system'; rm '#s/nix9-system'")
        guest.command("nix9-rebuild rollback")
        selected(guest, "one", first)
        guest.command("nix9-rebuild switch /tmp/two.nix")
        guest.command(f"test ! -e {SYSTEM}.generations/3")
        selected(guest, "two", second)
        login(guest, "two", second)
        guest.command(f"rm {ROOTS}/system-build /tmp/bootstrap.tar")
        guest.command("rm /tmp/systems.nix /tmp/one.nix /tmp/two.nix")
        guest.command("test ! -e /tmp/nix9-terminal-hook")
        guest.command("NIX_CONFIG='substituters ='; nix-store --gc")
        guest.command(f"nix-store --verify-path {first} {second}")
        print("PASS: system builds, activation, rejected updates, preserved hooks and generation reuse", flush=True)
    # No fixture server is running on subsequent boots.
    with boot(qemu, disk, snapshot=False, prompt=r"(?m)^(?:term)?% ") as guest:
        guest.child.timeout = 600
        guest.command("ip/ipconfig ether /net/ether0 unbind")
        guest.command("echo `{cat /dev/sysname}", "nix9-two")
        guest.command("cat /tmp/nix9-terminal-hook", "terminal")
        guest.command(f"cat {ROOTS}/system-boot", second)
        login(guest, "two", second)
        guest.command(". /usr/local/pkg/nix9/activate; NIX_CONFIG='substituters ='")
        guest.command("nix9-rebuild rollback")
        selected(guest, "one", first)
        rejected(guest, "nix9-rebuild delete 2", "cannot delete the booted generation")
        guest.command("nix-store --gc")
        guest.command(f"nix-store --verify-path {first} {second}")
    with boot(qemu, disk, snapshot=False, prompt=r"(?m)^(?:term)?% ") as guest:
        guest.child.timeout = 600
        guest.command("ip/ipconfig ether /net/ether0 unbind")
        guest.command("echo `{cat /dev/sysname}", "nix9")
        guest.command("cat /tmp/nix9-native-termrc", "device-setup")
        guest.command(f"cat {ROOTS}/system-boot", first)
        login(guest, "one", first)
        guest.command(". /usr/local/pkg/nix9/activate; NIX_CONFIG='substituters ='")
        guest.command("nix9-rebuild delete 2; nix-store --gc")
        guest.command(f"test ! -e {second}")
        guest.command(f"nix-store --verify-path {first}")
        selected(guest, "one", first)
        rejected(guest, "nix9-rebuild rollback", "no previous generation")
        guest.command("test ! -e '#s/nix9-system'")
        print("PASS: automatic boot activation, offline logins, rollback and boot-root GC retention", flush=True)

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "configuration": "packages, hostname, generated files and webfs certificate pins passed",
    "updates": "build, switch, rejected updates, generation reuse and rollback passed",
    "startup": "existing terminal and login hooks preserved; edited hooks rejected",
    "offline-reboot": "automatic hostname and login activation passed with Ethernet unbound",
    "gc": "booted generation retained; inactive generation collected after reboot",
}, indent=2) + "\n")
