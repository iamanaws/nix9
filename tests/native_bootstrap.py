"""Install the bootstrap archive in a clean VM and build a project natively."""

import json
from pathlib import Path
import re
import sys

from guest import files_guest


def rooted(guest, root):
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing output root: {result}")
    return paths[0]


qemu, image, archive, output = sys.argv[1:]
roots = "/usr/local/nix/state/gcroots"
with files_guest(qemu, image, {"bootstrap.tar": archive}) as guest:
    guest.child.timeout = 300
    guest.command("test ! -e /usr/local/nix/store")
    guest.command("cd / && tar xf /tmp/bootstrap.tar; rm /tmp/bootstrap.tar")
    guest.command(". /usr/local/pkg/nix9/activate")
    guest.command("nix-instantiate --eval --expr '(import <nix9>).stdenv.cc.name'", '"cc"')
    for name in ("environment", "shell"):
        result = guest.command(f"nix-build $nix9/{name}.nix --out-link {roots}/{name}")
        if "copying path" not in result or "building '" in result:
            raise RuntimeError(f"{name} did not substitute from the shipped cache: {result}")
    environment = rooted(guest, roots + "/environment")
    shell = rooted(guest, roots + "/shell")
    guest.command("rm -r $nix9/cache; NIX_CONFIG='substituters ='")
    guest.command(f"nix-profile {roots}/profile set {environment}")
    guest.command(f". $nix9/packages/profile {roots}/profile")
    guest.command("echo -n abc | sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
    guest.command("mkdir /tmp/hello; cp $nix9/hello/* /tmp/hello; cd /tmp/hello")
    result = guest.command(f"nix-build --out-link {roots}/hello")
    if "building '" not in result or re.search(r"building '[^']*-(cc|libc|mk)\.drv'", result):
        raise RuntimeError(f"project did not reuse the cached toolchain: {result}")
    hello = rooted(guest, roots + "/hello")
    guest.command(f"{hello}/bin/hello", "hello from nix9")
    guest.command("nix-shell --run 'mk && ./6.out && mk clean'", "hello from nix9")
    # Edit a user's environment, switch generations, then roll back after GC.
    guest.command("echo 'let p=import <nix9>; in p.buildEnv { name=\"updated-tools\"; paths=[p.fortune]; }' > /tmp/update.nix")
    guest.command(f"nix-build /tmp/update.nix --out-link {roots}/update")
    update = rooted(guest, roots + "/update")
    guest.command(f"nix-profile {roots}/profile set {update}")
    guest.command(f". $nix9/packages/profile {roots}/profile")
    if "/usr/local/nix/store/" in guest.command("whatis sha1sum"):
        raise RuntimeError("the previous environment's sha1sum is still active")
    guest.command("nix-store --gc")
    guest.command(f"nix-profile {roots}/profile rollback")
    guest.command(f". $nix9/packages/profile {roots}/profile")
    guest.command("echo -n abc | sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
    guest.command(f"nix-store --verify-path {environment} {shell} {hello}")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "clean-install": "passed",
    "native-project": "passed",
    "update-and-rollback": "passed",
}, indent=2) + "\n")
