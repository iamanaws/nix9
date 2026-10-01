"""Compare POSIX C operations in cross-built and guest-built APE programs."""

import functools
import http.server
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

from guest import boot


EXPECTED = [
    "PASS: memory allocation",
    "PASS: buffered file IO",
    "PASS: file descriptors and errno",
    "PASS: pipe fork exec and wait",
]


def main():
    qemu, disk, source, cross, output_dir = sys.argv[1:]
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        shutil.copyfile(source, Path(directory) / "main.c")
        shutil.copyfile(cross, Path(directory) / "cross")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    guest.command("mkdir /tmp/ape")
                    url = f"http://10.0.2.2:{server.server_port}"
                    for name in ("main.c", "cross"):
                        guest.command(f"hget -o /tmp/ape/{name} {url}/{name}")
                    guest.command("chmod +x /tmp/ape/cross")
                    guest.command("cd /tmp/ape && pcc -o native main.c")
                    for name in ("native", "cross"):
                        guest.command(f"mkdir /tmp/ape/{name}-work")
                        output = guest.command(f"cd /tmp/ape/{name}-work && /tmp/ape/{name}")
                        lines = [line for line in output.splitlines() if line.startswith("PASS:")]
                        if lines != EXPECTED:
                            raise RuntimeError(f"{name}: unexpected results: {lines!r}")
                        results[name] = lines
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nPASS: 4 POSIX groups passed in both native and cross APE builds")


if __name__ == "__main__":
    main()
