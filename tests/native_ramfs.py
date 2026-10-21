"""Build ramfs and check that private mounts and server processes disappear."""

import json
from pathlib import Path
import re
import sys
import time

from guest import files_guest


def servers(result):
    return set(re.findall(r"(?m)^\S+\s+(\d+)\s+.*\sramfs\s*$", result))


def wait_for_servers(guest, expected):
    for attempt in range(20):
        if servers(guest.command("ps")) == expected:
            return
        time.sleep(0.05)
    raise RuntimeError("ramfs server survived its namespace")


qemu, image, archive, output = sys.argv[1:]
fixtures = {"bootstrap.tar": archive}
roots = "/usr/local/nix/state/gcroots"
with files_guest(qemu, image, fixtures) as guest:
    guest.child.timeout = 600
    guest.command("cd / && tar xf /tmp/bootstrap.tar")
    guest.command(". /usr/local/pkg/nix9/activate")
    guest.command(f"nix-build $nix9/shell.nix --out-link {roots}/toolchain")
    guest.command("NIX_CONFIG='substituters ='")
    guest.command(f"nix-build $nix9/ramfs --out-link {roots}/ramfs")
    guest.command(f"environment=`{{cat {roots}/ramfs}}")
    for name in ("libauth", "libthread", "lib9p", "ramfs"):
        guest.command(f"nix-build '<nix9>' -A {name} --check --no-out-link")
    before = servers(guest.command("ps"))
    namespace = guest.command("cat /proc/$pid/ns")
    result = guest.command("@{ rfork ne; . $environment/activate; ramfs -m /mnt; ps; unmount /mnt }")
    if len(servers(result) - before) != 1:
        raise RuntimeError(f"missing live ramfs server: {result}")
    wait_for_servers(guest, before)
    for _ in range(2):
        guest.command("rc $nix9/ramfs/run.rc $environment", "Hello from ramfs")
        guest.command("test ! -f /mnt/hello")
        if guest.command("cat /proc/$pid/ns") != namespace:
            raise RuntimeError("service changed the parent namespace")
        wait_for_servers(guest, before)
    result = guest.command("@{ rfork ne; . $environment/activate; ramfs -m /mnt; ps; exit deliberate }; echo SERVICE-STATUS:$status")
    if not re.search(r"(?m)^SERVICE-STATUS:.*deliberate$", result):
        raise RuntimeError(f"missing service failure: {result}")
    if len(servers(result) - before) != 1:
        raise RuntimeError(f"missing live ramfs server before failure: {result}")
    wait_for_servers(guest, before)
    if guest.command("cat /proc/$pid/ns") != namespace:
        raise RuntimeError("failed service changed the parent namespace")
    guest.command("test ! -f /mnt/hello")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "ramfs": "native build, private mount, read/write, unmount and namespace exit passed",
}, indent=2) + "\n")
