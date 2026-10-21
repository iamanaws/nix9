"""Select complete releases, reboot offline and roll back using ordinary profiles."""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from guest import boot, files_guest


def rooted(guest, root):
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing release root: {result}")
    return paths[0]


def selected(guest, release, version, previous=None):
    guest.command("echo $nix9", release)
    guest.command("echo $NIX_CONF_DIR", release)
    guest.command("nix-instantiate --eval --expr '(import <nix9>).releaseTest or \"one\"'", f'"{version}"')
    guest.command("whatis nix-instantiate", release + "/bin/nix-instantiate")
    if previous and previous + "/bin" in guest.command("echo $path"):
        raise RuntimeError("previous release remains in the command path")


qemu, image, archive, output = sys.argv[1:]
roots = "/usr/local/nix/state/gcroots"
profile = roots + "/nix9"
with tempfile.TemporaryDirectory() as directory:
    disk = Path(directory) / "releases.qcow2"
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    fixtures = {"bootstrap.tar": archive, "releases.nix": Path(__file__).with_name("releases.nix")}
    with files_guest(qemu, disk, fixtures, snapshot=False) as guest:
        guest.child.timeout = 600
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate; bootstrap=$nix9")
        guest.command(f"nix-build /usr/local/pkg/nix9/release.nix --out-link {roots}/candidate")
        first = rooted(guest, roots + "/candidate")
        guest.command(f"nix-profile {profile} set {first}")
        guest.command(". /usr/local/pkg/nix9/activate")
        selected(guest, first, "one")
        guest.command(f"nix-build $nix9/release.nix --out-link {roots}/candidate")
        if rooted(guest, roots + "/candidate") != first:
            raise RuntimeError("rebuilding an installed release changed its output")
        guest.command(f"nix-build $nix9/environment.nix --out-link {roots}/environment")
        guest.command(f". $nix9/packages/profile {roots}/environment")
        guest.command(f"nix-build /tmp/releases.nix --out-link {roots}/candidate")
        second = rooted(guest, roots + "/candidate")
        if second == first:
            raise RuntimeError("upgrade fixture reused the original release")
        # Installing an archive must not overwrite the user's selected release.
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate")
        selected(guest, first, "one")
        guest.command(f"nix-profile {profile} set {second}")
        guest.command(". /usr/local/pkg/nix9/activate")
        selected(guest, second, "two", first)
        guest.command(f". $nix9/packages/profile {roots}/environment")
        selected(guest, second, "two", first)
        guest.command("mkdir -p /tmp/nix9-login/lib")
        guest.command("echo '. /usr/local/pkg/nix9/activate' > /tmp/nix9-login/lib/profile")
        guest.command(f"rm {roots}/candidate /tmp/bootstrap.tar; rm -r $bootstrap")
        guest.command("nix-store --gc")
        guest.command(f"nix-store --verify-path {first} {second}")
    # The following boots have no host file server or bootstrap installation.
    with boot(qemu, disk, snapshot=False) as guest:
        guest.child.timeout = 300
        guest.command("@{ home=/tmp/nix9-login; rc -el -c 'echo $nix9; nix-instantiate --eval --expr 42' }", second)
        guest.command(". /usr/local/pkg/nix9/activate")
        selected(guest, second, "two")
        guest.command("mkdir /tmp/hello; cp $nix9/hello/* /tmp/hello; cd /tmp/hello")
        guest.command("nix-shell --run 'mk && ./6.out && mk clean'", "hello from nix9")
        guest.command("cd /")
        guest.command(f"nix-profile {profile} rollback")
        guest.command(". /usr/local/pkg/nix9/activate")
        selected(guest, first, "one", second)
        guest.command(f"nix-profile {profile} delete 2")
        guest.command("nix-store --gc")
        guest.command(f"test ! -e {second} && nix-store --verify-path {first}")
    with boot(qemu, disk, snapshot=False) as guest:
        guest.command("@{ home=/tmp/nix9-login; rc -el -c 'echo $nix9; nix-instantiate --eval --expr 42' }", first)
        guest.command(". /usr/local/pkg/nix9/activate")
        selected(guest, first, "one")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "release-selection": "passed",
    "offline-reboots": "passed",
    "rollback-and-gc": "passed",
}, indent=2) + "\n")
