"""Probe the cc9-v0.2.2 binary release in a disposable guest.

Usage: python tests/cxx.py QEMU DISK cc9-amd64.tar.gz
Requires pexpect. Download the release linked in docs/feasibility.md first.
"""

import functools
import contextlib
import hashlib
import http.server
from pathlib import Path
import shutil
import sys
import tempfile
import threading

from guest import boot


@contextlib.contextmanager
def cc9_guest(qemu, disk, archive, files):
    digest = "dd6b7b7be9c544740e57fdbd207dcbf50eadc751ab805452d05b47884c22d184"
    with open(archive, "rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != digest:
            raise SystemExit("expected cc9-v0.2.2 archive")

    with tempfile.TemporaryDirectory() as directory:
        shutil.copyfile(archive, Path(directory) / "cc9.tar.gz")
        for name, source in files.items():
            shutil.copyfile(source, Path(directory) / name)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with boot(qemu, disk) as guest:
                    guest.child.timeout = 300
                    url = f"http://10.0.2.2:{server.server_port}"
                    guest.command(f"hget -o /tmp/cc9.tar.gz {url}/cc9.tar.gz")
                    guest.command("gunzip -c /tmp/cc9.tar.gz > /tmp/cc9.tar")
                    guest.command("cd / && tar xf /tmp/cc9.tar")
                    for name in files:
                        guest.command(f"hget -o /tmp/{name} {url}/{name}")
                    yield guest
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    with cc9_guest(*sys.argv[1:], {"probe.cpp": Path(__file__).parent / "cxx/probe.cpp"}) as guest:
        guest.command("/amd64/bin/cc /tmp/probe.cpp -o /tmp/probe")
        guest.command("/tmp/probe", "cxx23 threads tls exceptions files PASS")
