"""Compare native, cross-compiled, and mixed-compiler C objects in 9front."""

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
    "PASS: arguments and data model",
    "PASS: integer calls and recursion",
    "PASS: pointers and callbacks",
    "PASS: structures by value and return",
    "PASS: floating point",
    "PASS: varargs and libc calls",
]


def main():
    qemu, disk, sources, cross, output_dir = sys.argv[1:]
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        for name in ("main.c", "callee.c", "abi.h"):
            shutil.copyfile(Path(sources) / name, Path(directory) / name)
        for name in ("main.6", "callee.6", "abi-tests"):
            shutil.copyfile(Path(cross) / name, Path(directory) / name)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    url = f"http://10.0.2.2:{server.server_port}"
                    guest.command("mkdir /tmp/abi")
                    for name in ("main.c", "callee.c", "abi.h", "main.6", "callee.6", "abi-tests"):
                        guest.command(f"hget -o /tmp/abi/{name} {url}/{name}")
                    guest.command("cd /tmp/abi && 6c -o native-main.6 main.c")
                    guest.command("cd /tmp/abi && 6c -o native-callee.6 callee.c")
                    combinations = {
                        "native": "native-main.6 native-callee.6",
                        "cross-caller": "main.6 native-callee.6",
                        "native-caller": "native-main.6 callee.6",
                    }
                    for name, objects in combinations.items():
                        guest.command(f"cd /tmp/abi && 6l -o {name} {objects}")
                    guest.command("chmod +x /tmp/abi/abi-tests")
                    for name in ("native", "cross-caller", "native-caller", "abi-tests"):
                        output = guest.command(f"/tmp/abi/{name} alpha 23")
                        lines = [line for line in output.splitlines() if line.startswith("PASS:")]
                        if lines != EXPECTED:
                            raise RuntimeError(f"{name}: unexpected results: {lines!r}")
                        results[name] = lines
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nPASS: 6 ABI groups agree across native, cross, and both mixed builds")


if __name__ == "__main__":
    main()
