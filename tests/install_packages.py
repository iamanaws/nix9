"""Install and activate two packages together in a fresh 9front guest."""

import functools
import hashlib
import http.server
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

from guest import boot


def main():
    qemu, disk, archive, prefix, sums_archive, sums_prefix, fixture, output_dir = sys.argv[1:]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(archive, root / "package.tar")
        shutil.copyfile(sums_archive, root / "sums.tar")
        (root / "payload").write_bytes(b"abc")
        digest = hashlib.sha1(b"abc").hexdigest()
        shutil.copyfile(fixture, root / "fixture.lua")
        (root / "check.lua").write_text(
            'assert(require("fixture").twice(21) == 42)\n'
            f'local f = assert(io.open("{prefix}/share/doc/lua/readme.html"))\n'
            'assert(f:read("a"):find("Lua 5.4", 1, true))\n'
            'assert(f:close())\n'
            'print("PASS: installed Lua module and documentation")\n'
            'local lookup = assert(io.popen("command -v sha1sum", "r"))\n'
            f'assert(lookup:read("l") == "{sums_prefix}/bin/sha1sum")\n'
            'assert(lookup:close())\n'
            'local pipe = assert(io.popen("sha1sum /tmp/payload", "r"))\n'
            f'assert(pipe:read("l") == "{digest}\\t/tmp/payload")\n'
            'assert(pipe:close())\n'
            'print("PASS: installed packages work together")\n'
        )
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    url = f"http://10.0.2.2:{server.server_port}"
                    guest.command(f"hget -o /tmp/package.tar {url}/package.tar")
                    guest.command("cd / && tar xf /tmp/package.tar")
                    guest.command(f". {prefix}/activate")
                    guest.command("cd /tmp")
                    guest.command("lua -e 'print(6 * 7)'", expected="42")
                    guest.command(f"hget -o /tmp/sums.tar {url}/sums.tar")
                    guest.command("cd / && tar xf /tmp/sums.tar")
                    guest.command(f". {sums_prefix}/activate")
                    guest.command("whatis sha1sum", expected=f"{sums_prefix}/bin/sha1sum")
                    guest.command("whatis lua", expected=f"{prefix}/bin/lua")
                    guest.command(f"hget -o /tmp/payload {url}/payload")
                    guest.command("sha1sum /tmp/payload", expected=f"{digest}\t/tmp/payload")
                    # A module installed beside Lua must be found without path overrides.
                    guest.command(f"hget -o {prefix}/share/lua/5.4/fixture.lua {url}/fixture.lua")
                    guest.command(f"hget -o /tmp/check.lua {url}/check.lua")
                    guest.command("lua /tmp/check.lua",
                                  expected="PASS: installed packages work together")
                    guest.command("rm /tmp/package.tar /tmp/sums.tar /tmp/check.lua")
                    guest.command("cd / && lua -e 'print(require(\"fixture\").twice(21))'",
                                  expected="42")
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps({
        "prefix": prefix,
        "checksum-prefix": sums_prefix,
        "executable": "passed",
        "module-search": "passed",
        "documentation": "passed",
        "independent-of-working-directory": "passed",
        "activation-and-subprocess-lookup": "passed",
    }, indent=2) + "\n")
    print("\nPASS: installed packages work together in 9front")


if __name__ == "__main__":
    main()
