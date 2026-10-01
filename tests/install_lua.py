"""Unpack and use the Lua package in a fresh 9front guest."""

import functools
import http.server
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

from guest import boot


def main():
    qemu, disk, archive, prefix, fixture, output_dir = sys.argv[1:]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(archive, root / "package.tar")
        shutil.copyfile(fixture, root / "fixture.lua")
        (root / "check.lua").write_text(
            'assert(require("fixture").twice(21) == 42)\n'
            f'local f = assert(io.open("{prefix}/share/doc/lua/readme.html"))\n'
            'assert(f:read("a"):find("Lua 5.4", 1, true))\n'
            'assert(f:close())\n'
            'print("PASS: installed Lua module and documentation")\n'
        )
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    url = f"http://10.0.2.2:{server.server_port}"
                    guest.command(f"hget -o /tmp/package.tar {url}/package.tar")
                    guest.command("cd / && tar xf /tmp/package.tar")
                    guest.command(f"path=({prefix}/bin $path)")
                    guest.command("cd /tmp")
                    guest.command("lua -e 'print(6 * 7)'", expected="42")
                    # A module installed beside Lua must be found without path overrides.
                    guest.command(f"hget -o {prefix}/share/lua/5.4/fixture.lua {url}/fixture.lua")
                    guest.command(f"hget -o /tmp/check.lua {url}/check.lua")
                    guest.command("lua /tmp/check.lua",
                                  expected="PASS: installed Lua module and documentation")
                    guest.command("rm /tmp/package.tar /tmp/check.lua")
                    guest.command("cd / && lua -e 'print(require(\"fixture\").twice(21))'",
                                  expected="42")
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps({
        "prefix": prefix,
        "executable": "passed",
        "module-search": "passed",
        "documentation": "passed",
        "independent-of-working-directory": "passed",
    }, indent=2) + "\n")
    print("\nPASS: installed Lua package works in 9front")


if __name__ == "__main__":
    main()
