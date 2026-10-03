"""Check cross-built and guest-built sha1sum against independent digests."""

import functools
import hashlib
import http.server
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading

from guest import boot


def expect_failure(guest, command, message):
    try:
        guest.command(command)
    except RuntimeError as error:
        if "guest command failed" not in str(error) or message not in str(error):
            raise
    else:
        raise AssertionError(f"command unexpectedly succeeded: {command}")


FIXTURES = {
    "empty": b"",
    "abc": b"abc",
    # Includes NULs, high bytes, and a partial block after multiple reads.
    "binary": bytes(range(256)) * 257 + b"tail\x00\xff",
}
ALGORITHMS = {
    "sha1": "",
    "sha224": "-2 224",
    "sha256": "-2 256",
    "sha384": "-2 384",
    "sha512": "-2 512",
}

def check_sha1sum(guest, binaries, directory):
    results = {}
    for build, executable in binaries.items():
        tests = {}
        for algorithm, flags in ALGORITHMS.items():
            hashes = {
                name: hashlib.new(algorithm, data).hexdigest()
                for name, data in FIXTURES.items()
            }
            paths = " ".join(f"{directory}/{name}" for name in FIXTURES)
            output = guest.command(f"{executable} {flags} {paths}")
            actual = [line for line in output.splitlines()
                      if re.fullmatch(rf"[0-9a-f]+\t{re.escape(directory)}/\w+", line)]
            expected = [f"{digest}\t{directory}/{name}" for name, digest in hashes.items()]
            if actual != expected:
                raise AssertionError(f"{build} {algorithm}: {actual!r} != {expected!r}")
            for name in FIXTURES:
                tests[f"{algorithm}/{name}"] = hashes[name]
            guest.command(
                f"{executable} {flags} <{directory}/binary",
                expected=hashes["binary"],
            )
            tests[f"{algorithm}/stdin"] = hashes["binary"]
        for name, arguments, message in (
            ("missing-file", f"{directory}/missing", "can't open"),
            ("invalid-algorithm", "-2 128", "unknown number of sha2 bits"),
            ("invalid-option", "-z", "usage"),
        ):
            expect_failure(guest, f"{executable} {arguments}", message)
            tests[name] = "rejected"
        results[build] = tests
    if results["native"] != results["cross"]:
        raise AssertionError("native and cross results differ")
    return results


def main():
    qemu, disk, source, binary, output_dir = sys.argv[1:]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(source, root / "sha1sum.c")
        shutil.copyfile(binary, root / "cross")
        for name, data in FIXTURES.items():
            (root / name).write_bytes(data)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    guest.command("mkdir /tmp/sums")
                    url = f"http://10.0.2.2:{server.server_port}"
                    for name in ("sha1sum.c", "cross", *FIXTURES):
                        if name == "empty":
                            guest.command("cat /dev/null >/tmp/sums/empty")
                        else:
                            guest.command(f"hget -o /tmp/sums/{name} {url}/{name}")
                    guest.command("chmod +x /tmp/sums/cross")
                    guest.command("cd /tmp/sums && 6c -o sum.6 sha1sum.c")
                    guest.command("cd /tmp/sums && 6l -o native sum.6")
                    results = check_sha1sum(guest, {name: f"/tmp/sums/{name}" for name in ("native", "cross")}, "/tmp/sums")
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nPASS: 23 checksum and error cases passed for both native and cross builds")


if __name__ == "__main__":
    main()
