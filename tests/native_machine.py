"""Initialize two machines sharing runtime files with local writable stores."""

import contextlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

from guest import boot, files_guest


def rejected(guest, command, reason):
    result = guest.command(command + "; echo MACHINE-ERROR:$status")
    if not re.search(r"(?m)^MACHINE-ERROR:.+", result) or reason not in result:
        raise RuntimeError(f"machine operation was not rejected: {command}: {result}")


def selected(guest, identity, version):
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("echo $nix9MachineId", identity)
    guest.command("echo $nix9SystemRoot", f"/usr/local/nix/state/gcroots/machines/{identity}/system")
    guest.command("cat /cfg/nix9/files/version", "machine-" + version)
    guest.command("test ! -e /usr/local/nix/state/shared-sentinel")


def overlay(qemu, image, destination):
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(destination)], check=True)


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_MACHINE_TEST_STATE")
with (contextlib.nullcontext(state) if state else tempfile.TemporaryDirectory()) as directory:
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    fixtures = {"bootstrap.tar": archive, "machines.nix": Path(__file__).with_name("machines.nix"),
                "machine-newns.c": Path(__file__).with_name("machine-newns.c")}
    with files_guest(qemu, image, {"bootstrap.tar": archive}, forward_port=port, compress=True) as server:
        server.child.timeout = 900
        server.command("cd / && tar xf /tmp/bootstrap.tar")
        server.command("mkdir -p /usr/local/nix/store /usr/local/nix/state /usr/local/nix/log /tmp/shared-service")
        server.command("echo shared > /usr/local/nix/state/shared-sentinel")
        server.command("echo '#!/bin/rc' > /tmp/shared-service/tcp17010")
        server.command("echo 'exec /bin/exportfs -r /usr/local' >> /tmp/shared-service/tcp17010")
        server.command("chmod 755 /tmp/shared-service/tcp17010")
        server.command("aux/listen -t /tmp/shared-service tcp")
        for _ in range(40):
            if re.search(r"^tcp\s+\d+\s+\S+\s+Listen\s+17010\s", server.command("netstat -n"), re.M):
                break
            server.command("sleep 0.05")
        else:
            raise RuntimeError("shared fixture listener did not start")
        # This private fixture exports runtime files without authentication.
        # Authentication and encrypted CPU transport have their own rcpu suite.
        for identity in ("cpu-a", "cpu-b"):
            disk = work / f"{identity}.qcow2"
            if disk.exists():
                raise RuntimeError(f"refusing to overwrite an existing VM: {disk}")
            overlay(qemu, image, disk)
            with files_guest(qemu, disk, fixtures, snapshot=False, compress=True) as guest:
                guest.child.timeout = 900
                guest.command("cd / && tar xf /tmp/bootstrap.tar")
                guest.command(". /usr/local/pkg/nix9/activate")
                guest.command("~ $#nix9SystemRoot 0")
                for action in ("list", "build /tmp/one.nix", "switch /tmp/one.nix", "rollback"):
                    rejected(guest, "nix9-rebuild " + action, "initialize this machine")
                guest.command("@{ status='' } > '#s/nix9-machine'")
                rejected(guest, f"nix9-rebuild init {identity}", "initialization is locked")
                guest.command("test ! -e /usr/local/nix/state/machine-id")
                guest.command("rm '#s/nix9-machine'")
                rejected(guest, "nix9-rebuild init _", "invalid machine identity")
                guest.command(f"nix9-rebuild init {identity}")
                guest.command(f"nix9-rebuild init {identity}")
                for name in ("one", "two", "wrong"):
                    guest.command(f"echo '(import ./machines.nix {{}}).{name}' > /tmp/{name}.nix")
                guest.command("nix9-rebuild switch /tmp/one.nix")
                guest.command("nix9-rebuild switch /tmp/two.nix")
                startup = [
                    "if(! grep -s '10.0.2.15' /net/ipselftab) ip/ipconfig ether /net/ether0",
                    f"srv -n tcp!10.0.2.2!{port} shared",
                    "mount -n /srv/shared /n/shared",
                    "@{ rfork n; srvfs machine-local /root/usr/local/nix }",
                    "bind /n/shared/pkg /usr/local/pkg",
                    "bind /n/shared/nix /usr/local/nix",
                    "nix9local=machine-local", f"nix9machine={identity}",
                ]
                guest.command("echo -n > /rc/bin/termrc.local.nix9-original")
                for line in startup:
                    guest.command("echo '" + line.replace("'", "''") + "' >> /rc/bin/termrc.local.nix9-original")
                guest.command(". /rc/bin/termrc.local.nix9-original")
                guest.command(". /usr/local/pkg/nix9/activate")
                guest.command("test ! -e /usr/local/nix/state/shared-sentinel")
                guest.command(f"nix9-rebuild init {identity}")
                guest.command("nix9-rebuild list", "2 * " + re.findall(
                    r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat $nix9SystemRoot"))[0])
                rejected(guest, "nix9-rebuild init other", "already fixed")
                rejected(guest, "nix9-rebuild switch /tmp/wrong.nix", "another machine")
                guest.command("nix9-rebuild rollback")
                selected(guest, identity, "one")
                if identity == "cpu-b":
                    guest.command("nix9-rebuild switch /tmp/two.nix")
                selected(guest, identity, "one" if identity == "cpu-a" else "two")
                rejected(guest, "@{ rfork e; nix9machine=other; . /usr/local/pkg/nix9/activate }", "machine setup failed")
                for line in ("mount -n /srv/shared /n/shared", "bind /n/shared/pkg /usr/local/pkg",
                             "bind /n/shared/nix /usr/local/nix"):
                    guest.command("echo '" + line + "' >> /lib/namespace.local")
                guest.command("cd /tmp && 6c machine-newns.c && 6l -o machine-newns machine-newns.6")
                guest.command("/tmp/machine-newns '. /usr/local/pkg/nix9/system; echo $nix9MachineId; cat /cfg/nix9/files/version'", identity)
                guest.command("9fs 9fat")
                guest.command("echo 'nix9local=machine-local' >> /n/9fat/plan9.ini")
                guest.command(f"echo 'nix9machine={identity}' >> /n/9fat/plan9.ini")
            with boot(qemu, disk, snapshot=False, configure_network=False, prompt=r"(?m)^(?:term)?% ") as guest:
                selected(guest, identity, "one" if identity == "cpu-a" else "two")
                guest.command("cat $nix9SystemRoot^-boot", re.findall(
                    r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat $nix9SystemRoot"))[0])
                guest.command("nix9-rebuild init " + identity)
                if identity == "cpu-a":
                    guest.command("nix9-rebuild switch /tmp/two.nix")
                    rejected(guest, "nix9-rebuild delete 1", "booted generation")
                    guest.command("nix-store --gc")
                    guest.command("nix9-rebuild rollback")
                    selected(guest, identity, "one")
        server.command("test ! -e /usr/local/nix/state/machine-id")
        server.command("test ! -e /usr/local/nix/state/gcroots/machines")
        server.command(". /usr/local/pkg/nix9/activate")
        server.command("nix9-rebuild init server-probe")
        server.command("nix9-rebuild init server-probe")
        server.command("test ! -e /usr/local/nix/state/db/db.sqlite")
        # Neither the second node nor the server identity may affect this node.
        with boot(qemu, work / "cpu-a.qcow2", snapshot=False, configure_network=False, prompt=r"(?m)^(?:term)?% ") as guest:
            selected(guest, "cpu-a", "one")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "status": "passed", "machines": 2, "reboots": 3,
    "shared-runtime-local-stores": "passed", "explicit-initialization": "passed",
    "stable-identity-and-newns": "passed", "independent-selections": "passed",
}, indent=2) + "\n")
