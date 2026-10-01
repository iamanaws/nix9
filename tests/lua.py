"""Build Lua with guest pcc and compare it with the Linux cross build."""

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
    qemu, disk, archive, cross, fixtures, output_dir = sys.argv[1:]
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
                    for name in ("source.tar", "cross", "check.lua", "fixture.lua",
                                 "stdin.lua", "syntax.lua", "error.lua"):
                        guest.command(f"hget -o /tmp/lua/{name} {url}/{name}")
                    guest.command("cd /tmp/lua && tar xf source.tar")
                    guest.command("chmod +x /tmp/lua/cross")
                    for unit in units:
                        guest.command(f"cd /tmp/lua && pcc -c {unit}.c")
                    guest.command("cd /tmp/lua && pcc -o native *.6")
                    for name in ("native", "cross"):
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
    print("\nPASS: 11 Lua groups passed in both native and cross builds")


if __name__ == "__main__":
    main()
