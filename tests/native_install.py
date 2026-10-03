"""Install native Nix and reuse a guest-built package after a clean reboot."""

import functools
import http.server
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from guest import boot
from native_fetch import fetch_fixtures, check_fetch


qemu, image, archive, prefix, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    disk = root / "persistent.qcow2"
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    shutil.copyfile(archive, root / "package.tar")
    fetch_fixtures(root)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with boot(qemu, disk, snapshot=False) as guest:
                guest.child.timeout = 300
                guest.command(f"hget -o /tmp/package.tar http://10.0.2.2:{server.server_port}/package.tar")
                guest.command("cd / && tar xf /tmp/package.tar")
                guest.command(f". {prefix}/activate")
                guest.command("nix-instantiate --eval --expr '6 * 7'", "42")
                fetching = check_fetch(guest, prefix, server.server_port)
                drv_root = "/usr/local/nix/state/gcroots/sha1sum-drv"
                guest.command(
                    f"nix-instantiate --add-root {drv_root} "
                    f"--expr '(import {prefix}/share/nix9).sha1sum'", drv_root)
                result = guest.command(f"cat {drv_root}")
                paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-sha1sum\.drv$", result)
                if len(paths) != 1:
                    raise RuntimeError(f"missing installed derivation: {result}")
                drv = paths[0]
                guest.command("nix-store --gc")
                guest.command(f"nix-store --check-validity {drv}")
                permanent = "/usr/local/nix/state/gcroots/sha1sum"
                guest.command(f"nix-store --realise {drv} --add-root {permanent}", permanent)
                result = guest.command(f"cat {permanent}")
                paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-sha1sum$", result)
                if len(paths) != 1:
                    raise RuntimeError(f"missing installed output: {result}")
                package = paths[0]
                guest.command(f"rm {drv_root}")
                guest.command(f"echo -n abc | {package}/bin/sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
                guest.command(f"nix-store --verify-path {drv} {package}")
                guest.command("rm /tmp/package.tar")
        finally:
            server.shutdown()
            thread.join()
    # A second QEMU process uses the same overlay, without any host file server.
    with boot(qemu, disk, snapshot=False) as guest:
        guest.command(f". {prefix}/activate")
        guest.command(f"cat {permanent}", package)
        guest.command("echo disposable > /tmp/gc-unused")
        result = guest.command("nix-store --add /tmp/gc-unused")
        unused = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-gc-unused$", result)
        if len(unused) != 1:
            raise RuntimeError(f"missing unrooted store path: {result}")
        guest.command("nix-store --gc")
        guest.command(f"test ! -e {unused[0]}")
        guest.command(f"nix-store --check-validity {drv} {package}")
        result = guest.command(f"nix-store --realise {drv}", package)
        if re.search(r"(?m)^building '", result):
            raise RuntimeError(f"persisted package was rebuilt: {result}")
        guest.command(f"nix-store --verify-path {drv} {package}")
        guest.command(f"echo -n abc | {package}/bin/sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
        guest.command(f"rm {permanent}")
        guest.command("nix-store --gc")
        guest.command(f"test ! -e {package} && test ! -e {drv}")

Path(output, "native-install.json").write_text(json.dumps({
    "prefix": prefix,
    "derivation": drv,
    "output": package,
    "installation": "passed",
    "fetching": fetching,
    "native-build": "passed",
    "gc-before-build": "passed",
    "reuse-after-reboot": "passed",
    "permanent-roots-and-gc": "passed",
}, indent=2) + "\n")
print("PASS: installed native Nix builds and reuses sha1sum after reboot")
