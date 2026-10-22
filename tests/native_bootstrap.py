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


qemu, image, archive, seed_mk, seed_rc, seed_cc, seed_ar, seed_libmach, compressed, output = sys.argv[1:]
roots = "/usr/local/nix/state/gcroots"
fixtures = {"bootstrap.tar": archive, "seed-mk": seed_mk, "seed-rc": seed_rc,
            "seed-ar": seed_ar, "seed-libmach.a": seed_libmach, "input.gz": compressed}
for name in ("6a", "6c", "6l"):
    fixtures[name] = Path(seed_cc) / "bin" / name
for name in ("rc.nix", "bootstrap-inputs.nix", "build-tools.nix", "build-tools.rc"):
    fixtures[name] = Path(__file__).with_name(name)
with files_guest(qemu, image, fixtures) as guest:
    guest.child.timeout = 300
    guest.command("test ! -e /usr/local/nix/store")
    guest.command("cd / && tar xf /tmp/bootstrap.tar; rm /tmp/bootstrap.tar")
    guest.command(". /usr/local/pkg/nix9/activate")
    guest.command("cmp /tmp/seed-mk $nix9/packages/tools/bootstrap/bin/mk")
    guest.command("cmp /tmp/seed-rc $nix9/packages/tools/bootstrap/rc/bin/rc")
    guest.command("cmp /tmp/seed-ar $nix9/packages/tools/bootstrap/bin/ar")
    guest.command("cmp /tmp/seed-libmach.a $nix9/packages/tools/bootstrap/lib/libmach.a")
    for name in ("6a", "6c", "6l"):
        guest.command(f"cmp /tmp/{name} $nix9/packages/tools/bootstrap/bin/{name}")
    guest.command("nix-instantiate --eval --expr '(import <nix9>).stdenv.cc.name'", '"cc"')
    for name in ("environment", "shell"):
        result = guest.command(f"nix-build $nix9/{name}.nix --out-link {roots}/{name}")
        if "copying path" not in result or "building '" in result:
            raise RuntimeError(f"{name} did not substitute from the shipped cache: {result}")
    environment = rooted(guest, roots + "/environment")
    shell = rooted(guest, roots + "/shell")
    guest.command("rm -r $nix9/cache; NIX_CONFIG='substituters ='")
    guest.command("nix-build /tmp/build-tools.nix --argstr packages $nix9/packages --arg compressed /tmp/input.gz --no-out-link", "build-tools-PASS")
    guest.command(f"nix-build $nix9/packages -A rc --out-link {roots}/rc")
    rc = rooted(guest, roots + "/rc")
    guest.command("nix-instantiate --eval --expr 'let p=import <nix9>; in p.stdenv.shell == p.rc + \"/bin/rc\"'", "true")
    guest.command("fn rcBuild { nix-build /tmp/rc.nix --argstr packages $nix9/packages $* }")
    guest.command(f"rcBuild -A program --out-link {roots}/rc-test", "native-rc-PASS")
    guest.command("nix-shell /tmp/rc.nix --argstr packages $nix9/packages -A shell --run '. $rcCheck'", "native-rc-PASS")
    guest.command(f"rcBuild -A rebuilt --out-link {roots}/rebuilt-rc")
    rebuilt_rc = rooted(guest, roots + "/rebuilt-rc")
    guest.command(f"cmp {rc}/bin/rc {rebuilt_rc}/bin/rc")
    guest.command(f"rm {roots}/rc {roots}/rc-test {roots}/rebuilt-rc")
    guest.command("fn inputBuild { nix-build /tmp/bootstrap-inputs.nix --argstr packages $nix9/packages $* }")
    guest.command(f"inputBuild -A declared --out-link {roots}/library-test")
    library_test = rooted(guest, roots + "/library-test")
    guest.command(f"{library_test}/bin/bio", "declared library PASS")
    result = guest.command("inputBuild -A undeclared --no-out-link; echo INPUT-STATUS:$status")
    if "libbio.a" not in result or not re.search(r"(?m)^INPUT-STATUS:.*cc9exit=100$", result):
        raise RuntimeError(f"undeclared library was accepted: {result}")
    guest.command(f"inputBuild -A ape --out-link {roots}/ape-test")
    guest.command(f"`{{cat {roots}/ape-test}}", "APE runtime PASS")
    guest.command(f"rm {roots}/ape-test")
    guest.command(f"rm {roots}/library-test")
    guest.command("nix-build $nix9/packages -A sha1sum --check --no-out-link")
    guest.command(f"nix-build $nix9/packages -A sha1sum --out-link {roots}/sha1sum")
    guest.command(f"sum=`{{cat {roots}/sha1sum}}; chmod 666 $sum/bin/sha1sum; echo damaged > $sum/bin/sha1sum")
    result = guest.command("nix-build $nix9/packages -A sha1sum --repair --no-out-link")
    if "repairing outputs of" not in result or "copying path" in result:
        raise RuntimeError(f"damaged package was not rebuilt offline: {result}")
    guest.command("echo -n abc | $sum/bin/sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
    guest.command(f"nix-store --verify-path $sum; rm {roots}/sha1sum")
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
    "rebuilt-shell": "passed",
    "declared-build-inputs": "passed",
    "update-and-rollback": "passed",
}, indent=2) + "\n")
