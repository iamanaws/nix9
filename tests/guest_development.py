"""Compile native and POSIX C using the installed development environment."""

import functools
import http.server
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

from c_abi import EXPECTED
from ape import EXPECTED as APE_EXPECTED
from guest import boot


def main():
    qemu, disk, archive, environment, prefix, hello, abi, ape, bsd, output_dir = sys.argv[1:]
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(archive, root / "development.tar")
        shutil.copyfile(hello, root / "hello.c")
        shutil.copyfile(ape, root / "posix.c")
        shutil.copyfile(bsd, root / "bsd.c")
        for name in ("main.c", "callee.c", "abi.h"):
            shutil.copyfile(Path(abi) / name, root / name)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    url = f"http://10.0.2.2:{server.server_port}"
                    guest.command(f"hget -o /tmp/development.tar {url}/development.tar")
                    guest.command("cd / && tar xf /tmp/development.tar")
                    guest.command(f". {environment}/activate")
                    for tool in ("6c", "6l", "pcc"):
                        guest.command(f"whatis {tool}", expected=f"{prefix}/bin/{tool}")
                    guest.command("mkdir /tmp/build /tmp/empty")
                    for name in ("hello.c", "main.c", "callee.c", "abi.h", "posix.c", "bsd.c"):
                        guest.command(f"hget -o /tmp/build/{name} {url}/{name}")
                    # Hide the image's headers and libraries in this disposable namespace.
                    for path in ("/sys/include", "/amd64/include", "/amd64/lib"):
                        guest.command(f"bind /tmp/empty {path}")
                    guest.command("cd /tmp/build")
                    guest.command("6c -o hello.6 hello.c")
                    guest.command("6l -o hello hello.6")
                    output = guest.command("./hello", expected="Hello from Nix-built C on 9front/amd64!")
                    for line in ("PASS: C file create/write/seek/read/remove", "PASS: C pipe/fork/exec/wait"):
                        if line not in output.splitlines():
                            raise RuntimeError(f"missing guest result: {line}")
                    results["file-and-process-operations"] = "passed"
                    guest.command("6c -o main.6 main.c")
                    guest.command("6c -o callee.6 callee.c")
                    guest.command("6l -o abi main.6 callee.6")
                    output = guest.command("./abi alpha 23")
                    lines = [line for line in output.splitlines() if line.startswith("PASS:")]
                    if lines != EXPECTED:
                        raise RuntimeError(f"unexpected ABI results: {lines!r}")
                    results["abi"] = lines
                    for name, commands in {
                        "ape-direct": ("pcc -o ape-direct posix.c",),
                        "ape-separate": ("pcc -c -o posix.6 posix.c", "pcc -o ape-separate posix.6"),
                    }.items():
                        for command in commands:
                            guest.command(command)
                        output = guest.command(f"./{name}")
                        lines = [line for line in output.splitlines() if line.startswith("PASS:")]
                        if lines != APE_EXPECTED:
                            raise RuntimeError(f"unexpected {name} results: {lines!r}")
                        results[name] = lines
                    guest.command("pcc -o bsd bsd.c")
                    guest.command("./bsd", expected="PASS: APE headers and BSD subprocess I/O")
                    results["ape-bsd"] = "passed"
                    # The pcc wrapper's bindings must not escape to the caller.
                    for path in ("/sys/include/ape/stdio.h", "/amd64/include/u.h", "/amd64/lib/ape/libap.a"):
                        guest.command(f"test ! -e {path}")
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nPASS: guest C and APE builds use installed headers and rebuilt runtimes")


if __name__ == "__main__":
    main()
