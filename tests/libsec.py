"""Check libsec vectors and multiprecision arithmetic with both libraries."""

import functools
import http.server
import json
from pathlib import Path
import sys
import threading

from guest import boot


def check_native(guest, packages, port):
    guest.command("mkdir -p /tmp/crypto-tests")
    for name in ("native.nix", "mp.c"):
        guest.command(f"hget -o /tmp/crypto-tests/{name} http://10.0.2.2:{port}/libsec/{name}")
    root = "/usr/local/nix/state/gcroots/crypto-tests"
    command = f"nix-build /tmp/crypto-tests/native.nix --argstr packages {packages} --out-link {root}"
    guest.command(command)
    guest.command(f"cat `{{cat {root}}}", "passed")
    if "building '" in guest.command(command):
        raise RuntimeError("unchanged crypto tests were rebuilt")
    guest.command(f"rm {root}")
    return "native libsec and libmp, six crypto suites and build reuse passed"


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
                for test in ("sha2", "hmac", "chacha", "aesgcm", "eg", "mp"):
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
    print("\nPASS: six libsec and libmp suites passed in native and cross builds")


if __name__ == "__main__":
    main()
