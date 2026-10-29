"""Prepare persistent directories without changing their contents or bypassing native permissions."""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from guest import boot, files_guest


ROOT = "/usr/local/nix/state/gcroots/machines/test/system"
DATA = "/usr/glenda/nix9-state"


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def rejected(guest, command, reason):
    result = guest.command("rc -c " + quote(command) + "; echo DIRECTORY-ERROR:$status")
    if not re.search(r"(?m)^DIRECTORY-ERROR:.+", result) or reason not in result or "syntax error" in result:
        raise RuntimeError(f"operation did not reject {reason}: {result}")
    guest.command("test ! -e '#s/nix9-system-test'")


def root(guest, suffix=""):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat " + ROOT + suffix))
    if len(paths) != 1:
        raise RuntimeError("missing system root")
    return paths[0]


def mode(guest, path, permissions, owner=None, group=None, prefix="d"):
    guest.command("ls -ld " + path + " | awk '{print $1}'", prefix + permissions)
    if owner:
        guest.command("ls -ld " + path + " | awk '{print $4}'", owner)
    if group:
        guest.command("ls -ld " + path + " | awk '{print $5}'", group)


def contents(guest):
    guest.command("cat " + DATA + "/nested/deeper/user-data", "persistent-user-data")
    mode(guest, DATA + "/nested/deeper/user-data", "-rw-------", prefix="-")
    guest.command("cat /usr/glenda/nix9-preserved/existing", "existing-data")
    mode(guest, "/usr/glenda/nix9-preserved", "-rwx------", "glenda", "sys")
    guest.command("cat /usr/glenda/nix9-only-one/kept", "kept-after-removal")


qemu, image, archive, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    disk = Path(directory) / "directories.qcow2"
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    fixtures = {"bootstrap.tar": archive, "directories.nix": Path(__file__).with_name("directories.nix"),
                "directory-checks.nix": Path(__file__).with_name("directory-checks.nix"),
                "directory-mounted.rc": Path(__file__).with_name("directory-mounted.rc")}
    with files_guest(qemu, disk, fixtures, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init test")
        guest.command("nix-instantiate --eval --strict --json /tmp/directory-checks.nix")
        for name in ("one", "two", "removed", "conflict", "special", "deniedOwner", "unknownGroup"):
            guest.command(f"echo '(import ./directories.nix {{}}).{name}' > /tmp/{name}.nix")
        guest.command("mkdir -m 755 /usr/glenda/nix9-preserved; chgrp sys /usr/glenda/nix9-preserved")
        guest.command("echo existing-data > /usr/glenda/nix9-preserved/existing")
        guest.command("nix9-rebuild build /tmp/one.nix")
        one = root(guest, "-build")
        guest.command("nix9-rebuild check " + one)
        guest.command("test ! -e " + DATA + " && test ! -e /usr/glenda/nix9-recreated && test ! -e " + ROOT)
        mode(guest, "/usr/glenda/nix9-preserved", "-rwxr-xr-x", "glenda", "sys")
        guest.command("test ! -e /sys/log/nix9")
        guest.command("nix9-rebuild select " + one)
        mode(guest, DATA, "-rwxr-x---", "glenda", "sys")
        mode(guest, DATA + "/nested", "-rwxr-xr-x")
        mode(guest, DATA + "/nested/deeper", "-rwx--x---")
        guest.command("echo persistent-user-data > " + DATA + "/nested/deeper/user-data; chmod 600 " + DATA + "/nested/deeper/user-data")
        guest.command("echo kept-after-removal > /usr/glenda/nix9-only-one/kept")
        contents(guest)
        history = guest.command("nix9-rebuild list")
        guest.command("nix9-rebuild select " + one)
        if guest.command("nix9-rebuild list") != history:
            raise RuntimeError("repeated directory preparation changed history")
        guest.command("nix9-rebuild build /tmp/two.nix")
        two = root(guest, "-build")
        guest.command("nix9-rebuild check " + two)
        mode(guest, DATA, "-rwxr-x---", "glenda", "sys")
        guest.command("mkdir -m 700 /usr/glenda/nix9-bind-source")
        guest.command("echo mounted-data > /usr/glenda/nix9-bind-source/data")
        for mount in (DATA, DATA + "/nested"):
            for action in ("check", "select"):
                rejected(guest, f"rc /tmp/directory-mounted.rc {two} {action} {mount}", "retained session mount")
                mode(guest, "/usr/glenda/nix9-bind-source", "-rwx------")
                guest.command("cat /usr/glenda/nix9-bind-source/data", "mounted-data")
        guest.command("echo conflict > /usr/glenda/nix9-z-conflict")
        guest.command("mkdir /usr/glenda/nix9-special; chmod +a /usr/glenda/nix9-special")
        for name in ("conflict", "special"):
            guest.command("nix9-rebuild build /tmp/" + name + ".nix")
            rejected(guest, "nix9-rebuild check " + root(guest, "-build"), "not a regular directory")
        for name, reason in (("conflict", "not a regular directory"), ("special", "not a regular directory"),
                             ("deniedOwner", "cannot set directory metadata"), ("unknownGroup", "cannot set directory metadata")):
            rejected(guest, "nix9-rebuild switch /tmp/" + name + ".nix", reason)
            guest.command("cat " + ROOT, one)
            if guest.command("nix9-rebuild list") != history:
                raise RuntimeError("rejected directory settings changed history")
            mode(guest, DATA, "-rwxr-x---", "glenda", "sys")
            contents(guest)
        guest.command("test ! -e /usr/glenda/nix9-a-new")
        guest.command("nix9-rebuild select " + two)
        mode(guest, DATA, "-rwx--x---", "glenda", "glenda")
        mode(guest, DATA + "/nested/deeper", "-rwxr-x---")
        contents(guest)
        guest.command("rm /usr/glenda/nix9-recreated; chmod 700 " + DATA)
        print("PASS: nonmutating checks, parent creation, native metadata, rejected conflicts, preserved contents and generation reuse", flush=True)
    selected = {"one": one, "two": two}
    for version in ("two", "one", "removed"):
        with boot(qemu, disk, snapshot=False, configure_network=False, prompt=r"(?m)^(?:term)?% ") as guest:
            guest.child.timeout = 600
            guest.command(". /usr/local/pkg/nix9/activate; NIX_CONFIG='substituters ='")
            guest.command("cat " + ROOT + "-boot", selected[version])
            contents(guest)
            mode(guest, "/usr/glenda/nix9-recreated", "-rwxr-x---")
            if version == "two":
                mode(guest, DATA, "-rwx--x---", "glenda", "glenda")
                guest.command("nix9-rebuild rollback")
                mode(guest, DATA, "-rwxr-x---", "glenda", "sys")
                guest.command("chmod 700 " + DATA)
            elif version == "one":
                mode(guest, DATA, "-rwxr-x---", "glenda", "sys")
                guest.command("nix9-rebuild switch /tmp/removed.nix")
                selected["removed"] = root(guest)
                contents(guest)
                mode(guest, DATA, "-rwxr-x---", "glenda", "sys")
            else:
                contents(guest)
                guest.command("test -d " + DATA + "/nested/deeper")
            guest.command("test ! -e '#s/nix9-system-test'")
    print("PASS: boot recreation, permission restoration, rollback and removal preserve all user data", flush=True)

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "status": "passed", "reboots": 3,
    "checks": ["native-evaluation", "check-without-mutation", "missing-parents", "metadata",
               "native-owner-rejection", "unknown-group", "file-conflicts", "special-directories", "retained-session-mounts",
               "nonrecursive-permissions", "generation-reuse", "boot-recreation", "rollback", "removal-keeps-data"],
}, indent=2) + "\n")
