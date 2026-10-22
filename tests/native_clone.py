"""Build upstream clone from pinned Git sources and copy files in a session."""

import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from guest import files_guest


qemu, image, archive, repository, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    shutil.copytree(Path(repository) / ".git", root / "clone.git")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    daemon = subprocess.Popen([
        "git", "daemon", "--export-all", "--listen=127.0.0.1",
        f"--port={port}", f"--base-path={root}", str(root),
    ])
    try:
        for attempt in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except ConnectionRefusedError:
                if daemon.poll() is not None:
                    raise RuntimeError("Git daemon stopped before accepting connections")
                time.sleep(0.05)
        else:
            raise RuntimeError("Git daemon did not start")
        (root / "payload").write_bytes(bytes(range(256)) * 2048)
        (root / "copy.rc").write_text('''#!/bin/rc -e
mkdir -p /mnt/source/nested
echo copied > /mnt/source/nested/message
cp /tmp/payload /mnt/source/payload
touch /mnt/source/empty
clone -b 4096 -p 2:4 /mnt/source /mnt/destination
cmp /mnt/source/nested/message /mnt/destination/nested/message
cmp /mnt/source/payload /mnt/destination/payload
test -f /mnt/destination/empty
test ! -s /mnt/destination/empty
echo replacement > /mnt/source/nested/message
clone /mnt/source/nested/message /mnt/destination/nested/message
cmp /mnt/source/nested/message /mnt/destination/nested/message
clone /mnt/source/payload /mnt/source/empty /mnt/multiple
cmp /mnt/source/payload /mnt/multiple/payload
test -f /mnt/multiple/empty
echo upstream-clone-PASS
''')
        fixtures = {
            "bootstrap.tar": archive,
            "clone.nix": Path(__file__).with_name("clone.nix"),
            "copy.rc": root / "copy.rc",
            "payload": root / "payload",
        }
        with files_guest(qemu, image, fixtures) as guest:
            guest.child.timeout = 600
            guest.command("cd / && tar xf /tmp/bootstrap.tar")
            guest.command(". /usr/local/pkg/nix9/activate")
            roots = "/usr/local/nix/state/gcroots"
            guest.command(f"nix-build $nix9/shell.nix --out-link {roots}/toolchain")
            guest.command("NIX_CONFIG='substituters ='")
            guest.command(f"url=git://10.0.2.2:{port}/clone.git")
            guest.command("fn cloneBuild { nix-build /tmp/clone.nix --argstr packages $nix9/packages --argstr url $url $* }")
            guest.command(f"cloneBuild -A environment --out-link {roots}/copy")
            guest.command(f"environment=`{{cat {roots}/copy}}")
            namespace = guest.command("cat /proc/$pid/ns")
            guest.command("$environment/session rc /tmp/copy.rc", "upstream-clone-PASS")
            guest.command("test ! -f /mnt/destination/payload")
            if guest.command("cat /proc/$pid/ns") != namespace:
                raise RuntimeError("copy session changed its parent's namespace")
            guest.command(f"cloneBuild -A clone --out-link {roots}/clone")
            guest.command(f"package=`{{cat {roots}/clone}}; test -s $package/man/1/clone")
            guest.command("test -s $package/share/doc/clone/LICENSE")
            guest.command("$package/bin/clone /tmp/payload /tmp/copied")
            guest.command("cmp /tmp/payload /tmp/copied")
            guest.command("mkdir -p /tmp/tree/nested; echo persistent > /tmp/tree/nested/message")
            guest.command("$package/bin/clone /tmp/tree /tmp/copied-tree")
            guest.command("cmp /tmp/tree/nested/message /tmp/copied-tree/nested/message")
            result = guest.command("$environment/session clone /tmp/nonexistent /mnt/missing; echo COPY-STATUS:$status")
            if not re.search(r"(?m)^COPY-STATUS:.+", result):
                raise RuntimeError("clone did not report a missing source")
            guest.command("cloneBuild -A clone --check --no-out-link")
            daemon.terminate()
            daemon.wait()
            guest.command("url=git://10.0.2.2:1/offline.git")
            guest.command("cloneBuild -A clone --check --no-out-link")
    finally:
        if daemon.poll() is None:
            daemon.terminate()
        daemon.wait()

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "clone": "pinned upstream Git source, native mk build, session copies, failure status, reproducible rebuild and offline source reuse passed",
}, indent=2) + "\n")
