"""Check libsec vectors and multiprecision arithmetic with both libraries."""

import functools
import http.server
import json
from pathlib import Path
import re
import sys
import threading

from guest import boot


def check_native(guest, packages, port):
    guest.command("mkdir -p /tmp/crypto-tests")
    for name in ("native.nix", "mp.c", "generated.sha256"):
        guest.command(f"hget -o /tmp/crypto-tests/{name} http://10.0.2.2:{port}/libsec/{name}")
    root = "/usr/local/nix/state/gcroots/crypto-tests"
    command = f"nix-build /tmp/crypto-tests/native.nix --argstr packages {packages} --out-link {root}"
    guest.command(command)
    guest.command(f"cat `{{cat {root}}}", "passed")
    if "building '" in guest.command(command):
        raise RuntimeError("unchanged crypto tests were rebuilt")
    guest.command(f"rm {root}")
    return "native mpc code generation, libsec and libmp, six crypto suites and build reuse passed"


def main():
    qemu, disk, tests, hashes, output_dir = sys.argv[1:]
    results = {}
    expected = dict(line.split()[::-1] for line in Path(hashes).read_text().splitlines())
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tests)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with boot(qemu, disk) as guest:
                url = f"http://10.0.2.2:{server.server_port}"
                guest.command("mkdir /tmp/sec")
                guest.command("cd /tmp/sec")
                guest.command(f"hget -o mpc {url}/bin/mpc && chmod +x mpc")
                guest.command("bind /dev/null /amd64/bin/mpc")
                guest.command("echo 'bases(a,b,c,d) { a=123; b=0x7b; c=0b1111011; d=0173; }' | ./mpc > bases.c")
                for name in ("a", "b", "c", "d"):
                    guest.command(f"grep 'uitomp[(]123UL, {name}[)];' bases.c")
                for unit in ("secp256r1", "secp384r1", "secp256k1", "jacobian"):
                    guest.command(f"hget -o {unit}.mp {url}/src/{unit}.mp")
                    guest.command(f"echo '#include \"os.h\"' > {unit}.c; echo '#include <mp.h>' >> {unit}.c")
                    guest.command(f"./mpc {unit}.mp >> {unit}.c")
                    guest.command(f"sha1sum -2 256 < {unit}.c", expected[unit + ".c"])
                    results[f"mpc/{unit}"] = "passed"
                result = guest.command("echo 'broken(' | ./mpc > /dev/null; echo MPC-STATUS:$status")
                if not re.search(r"(?m)^MPC-STATUS:.+", result):
                    raise RuntimeError("mpc accepted invalid input")
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
    print("\nPASS: cross-built mpc matches reference output; six libsec and libmp suites passed")


if __name__ == "__main__":
    main()
