"""Compare Lua built with stock, cross, and installed guest development tools."""

import functools
import http.server
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import threading

from guest import boot


EXPECTED = [
    "PASS: arguments and arithmetic",
    "PASS: tables strings and UTF-8",
    "PASS: binary file IO and errors",
    "PASS: Lua modules",
    "PASS: coroutines",
    "PASS: protected errors and closing",
    "PASS: bytecode and garbage collection",
    "PASS: subprocess pipes and exit status",
    "PASS: temporary files and UTC time",
]


def main():
    qemu, disk, archive, cross, fixtures, development, environment, prefix, output_dir = sys.argv[1:]
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        units = []
        with tarfile.open(archive) as source, tarfile.open(root / "source.tar", "w") as target:
            for member in source.getmembers():
                path = Path(member.name)
                if path.parent.name != "src" or path.suffix not in (".c", ".h"):
                    continue
                data = source.extractfile(member)
                entry = tarfile.TarInfo(path.name)
                entry.size = member.size
                target.addfile(entry, data)
                if path.suffix == ".c" and path.name != "luac.c":
                    units.append(path.stem)
        units.sort()
        shutil.copyfile(cross, root / "cross")
        shutil.copyfile(development, root / "development.tar")
        for name in ("check.lua", "fixture.lua"):
            shutil.copyfile(Path(fixtures) / name, root / name)
        (root / "stdin.lua").write_text("print(6 * 7)\n")
        (root / "syntax.lua").write_text("return (\n")
        (root / "error.lua").write_text("error('expected CLI failure')\n")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    guest.command("mkdir /tmp/lua")
                    url = f"http://10.0.2.2:{server.server_port}"
                    for name in ("source.tar", "development.tar", "cross", "check.lua", "fixture.lua",
                                 "stdin.lua", "syntax.lua", "error.lua"):
                        guest.command(f"hget -o /tmp/lua/{name} {url}/{name}")
                    guest.command("cd /tmp/lua && tar xf source.tar")
                    guest.command("chmod +x /tmp/lua/cross")
                    def build(name):
                        for unit in units:
                            guest.command(f"cd /tmp/lua && pcc -c {unit}.c")
                        guest.command(f"cd /tmp/lua && pcc -o {name} *.6")

                    build("native")
                    guest.command("cd / && tar xf /tmp/lua/development.tar")
                    guest.command(f". {environment}/activate")
                    guest.command("whatis pcc", expected=f"{prefix}/bin/pcc")
                    guest.command("mkdir /tmp/empty")
                    hidden = ("/sys/include", "/amd64/include", "/amd64/lib")
                    for path in hidden:
                        guest.command(f"bind /tmp/empty {path}")
                    # Remove the stock build's objects before compiling with the installed tools.
                    guest.command("cd /tmp/lua && rm *.6")
                    build("development")
                    for path in ("/sys/include/ape/stdio.h", "/amd64/include/u.h", "/amd64/lib/ape/libap.a"):
                        guest.command(f"test ! -e {path}")
                    for name in ("native", "cross", "development"):
                        guest.command(f"mkdir /tmp/lua/{name}-work")
                        command = f"cd /tmp/lua/{name}-work && /tmp/lua/{name}"
                        output = guest.command(f"{command} /tmp/lua/check.lua 23")
                        lines = [line for line in output.splitlines() if line.startswith("PASS:")]
                        if lines != EXPECTED:
                            raise RuntimeError(f"{name}: unexpected results: {lines!r}")
                        guest.command(f"{command} -e 'print(6 * 7)'", expected="42")
                        guest.command(f"{command} </tmp/lua/stdin.lua", expected="42")
                        for script in ("syntax.lua", "error.lua"):
                            try:
                                guest.command(f"{command} /tmp/lua/{script}")
                            except RuntimeError as error:
                                if "guest command failed" not in str(error):
                                    raise
                            else:
                                raise AssertionError(f"{name} accepted {script}")
                        results[name] = lines + ["PASS: CLI expression and stdin",
                                                "PASS: CLI syntax and runtime errors"]
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nPASS: 11 Lua groups passed in stock guest, cross, and installed development builds")


if __name__ == "__main__":
    main()
