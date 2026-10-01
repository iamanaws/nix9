"""Run upstream libsec vectors with guest and cross-built libraries."""

import functools
import http.server
import json
from pathlib import Path
import sys
import threading

from guest import boot


def main():
    qemu, disk, tests, output_dir = sys.argv[1:]
    results = {}
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tests)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with boot(qemu, disk) as guest:
                url = f"http://10.0.2.2:{server.server_port}"
                guest.command("mkdir /tmp/sec")
                guest.command("cd /tmp/sec")
                for test in ("sha2", "hmac", "chacha", "aesgcm"):
                    guest.command(f"hget -o {test}.c {url}/src/{test}.c")
                    guest.command(f"hget -o cross {url}/bin/{test}")
                    guest.command("chmod +x cross")
                    guest.command(f"6c -I /sys/src/libmp/port -o test.6 {test}.c")
                    guest.command("6l -o native test.6")
                    for build in ("native", "cross"):
                        guest.command(f"./{build}")
                        results[f"{test}/{build}"] = "passed"
        finally:
            server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nPASS: four upstream libsec vector suites passed in native and cross builds")


if __name__ == "__main__":
    main()
