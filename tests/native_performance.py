"""Measure a native development workflow on a persistent, disk-backed overlay."""

import functools
import http.server
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time

from guest import boot


def rooted(guest, root):
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing output root: {result}")
    return paths[0]


def main():
    qemu, image, archive, output = sys.argv[1:]
    output = Path(output).resolve()
    output.mkdir()
    timings = {}

    def measure(guest, name, command, expected=None):
        start = time.monotonic()
        result = guest.command(command, expected)
        seconds = round(time.monotonic() - start, 3)
        timings.setdefault(name, []).append(seconds)
        (output / "timings.json").write_text(json.dumps(timings, indent=2) + "\n")
        print(f"TIMING {name}: {seconds}s", flush=True)
        return result

    roots = "/usr/local/nix/state/gcroots"
    profile = roots + "/environment"

    def cached_build(guest, name):
        result = measure(guest, name, f"nix-build --out-link {roots}/hello", hello)
        if "building '" in result or "copying path" in result:
            raise RuntimeError(f"cached build rebuilt or downloaded an output: {result}")

    # Keep the VM on the output filesystem, independent of TMPDIR.
    with tempfile.TemporaryDirectory(dir=output) as directory:
        work = Path(directory)
        disk = work / "development.qcow2"
        subprocess.run([
            str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
            "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk),
        ], check=True)
        (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with boot(qemu, disk, snapshot=False) as guest:
                    guest.child.timeout = 600
                    url = f"http://10.0.2.2:{server.server_port}/bootstrap.tar"
                    measure(guest, "download-discard", f"hget -o /dev/null {url}")
                    measure(guest, "download-disk", f"hget -o /tmp/bootstrap.tar {url}")
                    measure(guest, "extract-bootstrap", "cd / && tar xf /tmp/bootstrap.tar")
                    guest.command("rm /tmp/bootstrap.tar; . /usr/local/pkg/nix9/activate")
                    for _ in range(3):
                        measure(guest, "eval-constant", "nix-instantiate --eval --expr 42", "42")
                        measure(guest, "eval-packages", "nix-instantiate --eval --expr '(import <nix9>).stdenv.cc.name'", '"cc"')
                    result = measure(guest, "import-environment", f"nix-build $nix9/environment.nix --out-link {roots}/candidate")
                    if "copying path" not in result or "building '" in result:
                        raise RuntimeError(f"environment did not use the bundled cache: {result}")
                    environment = rooted(guest, roots + "/candidate")
                    guest.command(f"nix-profile {profile} set {environment}")
                    guest.command(f". $nix9/packages/profile {profile}")
                    guest.command("echo -n abc | sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
                    guest.command("mkdir /tmp/hello; cp $nix9/hello/* /tmp/hello; cd /tmp/hello")
                    measure(guest, "source-import", "nix-store --add /tmp/hello")
                    measure(guest, "instantiate-project", "nix-instantiate default.nix")
                    measure(guest, "build-project", f"nix-build --out-link {roots}/hello")
                    hello = rooted(guest, roots + "/hello")
                    guest.command(f"{hello}/bin/hello", "hello from nix9")
                    for _ in range(3):
                        cached_build(guest, "cached-build")
                        measure(guest, "shell-startup", "nix-shell --run 'echo shell-ready'", "shell-ready")
                        measure(guest, "development-shell", "nix-shell --run 'mk && ./6.out && mk clean'", "hello from nix9")
                    guest.command("cd /")
                    guest.command('echo \'let p=import <nix9>; in p.buildEnv { name="updated-tools"; paths=[p.fortune]; }\' > /tmp/update.nix')
                    measure(guest, "build-update", f"nix-build /tmp/update.nix --out-link {roots}/candidate")
                    update = rooted(guest, roots + "/candidate")
                    guest.command(f"nix-profile {profile} set {update}")
                    guest.command(f"rm {roots}/candidate")
            finally:
                server.shutdown()
                thread.join()
        # There is no HTTP server for either reboot.
        with boot(qemu, disk, snapshot=False) as guest:
            guest.child.timeout = 600
            guest.command(". /usr/local/pkg/nix9/activate")
            guest.command("NIX_CONFIG='substituters ='")
            guest.command(f"cat {profile}", update)
            guest.command(f". $nix9/packages/profile {profile}")
            guest.command(f"{hello}/bin/hello", "hello from nix9")
            guest.command("cd /tmp/hello")
            cached_build(guest, "cached-build-after-reboot")
            measure(guest, "shell-after-reboot", "nix-shell --run 'mk && ./6.out && mk clean'", "hello from nix9")
            guest.command("cd /")
            measure(guest, "rollback", f"nix-profile {profile} rollback")
            guest.command(f"cat {profile}", environment)
            guest.command(f". $nix9/packages/profile {profile}")
            guest.command("echo -n abc | sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
            guest.command(f"nix-profile {profile} delete 2")
            measure(guest, "gc", "nix-store --gc")
            guest.command(f"test ! -e {update} && nix-store --verify-path {environment} {hello}")
        with boot(qemu, disk, snapshot=False) as guest:
            guest.command(". /usr/local/pkg/nix9/activate")
            guest.command(f"cat {profile}", environment)
            guest.command(f". $nix9/packages/profile {profile}")
            guest.command("echo -n abc | sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "check", str(disk)], check=True)
    (output / "results.json").write_text(json.dumps({
        "persistent-development": "passed",
        "offline-update-and-rollback": "passed",
        "bootstrap": str(Path(archive).resolve()),
        "bootstrap-bytes": Path(archive).stat().st_size,
        "vm-image": str(Path(image).resolve()),
        "seconds": timings,
    }, indent=2) + "\n")
    print(f"PASS: persistent development and rollback; results in {output / 'results.json'}")


if __name__ == "__main__":
    main()
