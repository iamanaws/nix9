"""Check native and cross-built static archives against Python bzip2 output."""

import bz2
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


UNITS = ("blocksort", "huffman", "crctable", "randtable", "compress", "decompress", "bzlib")


def main():
    qemu, disk, source, library, consumer, main_source, output_dir = sys.argv[1:]
    fixtures = {
        "empty": b"",
        "text": b"static libraries on 9front\n" * 100,
        "binary": bytes(range(256)) * 1025,
    }
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with tarfile.open(source) as upstream:
            for name in [f"{unit}.c" for unit in UNITS] + ["bzlib.h", "bzlib_private.h"]:
                with upstream.extractfile(f"bzip2-1.0.8/{name}") as data:
                    (root / name).write_bytes(data.read())
        shutil.copyfile(main_source, root / "main.c")
        shutil.copyfile(Path(library) / "lib/libbz2.a", root / "cross.a")
        shutil.copyfile(Path(consumer) / "main.6", root / "cross-main.6")
        shutil.copyfile(Path(consumer) / "bin/bz2-test", root / "cross")
        for name, data in fixtures.items():
            (root / name).write_bytes(data)
            for level in (1, 9):
                (root / f"{name}-bz{level}").write_bytes(bz2.compress(data, compresslevel=level))
        members = sorted(root.iterdir())
        with tarfile.open(root / "source.tar", "w") as archive:
            for member in members:
                archive.add(member, arcname=member.name)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    guest.command("mkdir /tmp/bz2")
                    guest.command(f"hget -o /tmp/bz2/source.tar http://10.0.2.2:{server.server_port}/source.tar")
                    guest.command("cd /tmp/bz2 && tar xf source.tar")
                    guest.command("chmod +x /tmp/bz2/cross")
                    for unit in UNITS:
                        guest.command(f"cd /tmp/bz2 && pcc -D_POSIX_SOURCE -c {unit}.c")
                    objects = " ".join(f"{unit}.6" for unit in UNITS)
                    guest.command(f"cd /tmp/bz2 && ar rc native.a {objects}")
                    guest.command("cd /tmp/bz2 && pcc -c -o native-main.6 main.c")
                    for name, objects in {
                        "native": "native-main.6 native.a",
                        "cross-library": "native-main.6 cross.a",
                        "native-library": "cross-main.6 native.a",
                    }.items():
                        guest.command(f"cd /tmp/bz2 && pcc -o {name} {objects}")
                    for build in ("native", "cross", "cross-library", "native-library"):
                        cases = []
                        prefix = f"cd /tmp/bz2 && ./{build}"
                        for name in fixtures:
                            guest.command(f"{prefix} compress {name} output")
                            guest.command(f"cd /tmp/bz2 && cmp output {name}-bz1")
                            cases.append(f"compress/{name}")
                            guest.command(f"{prefix} decompress {name}-bz9 output")
                            guest.command(f"cd /tmp/bz2 && cmp output {name}")
                            cases.append(f"decompress/{name}")
                        guest.command(f"{prefix} --errors", expected="PASS: libbz2 error handling")
                        cases.append("errors")
                        results[build] = cases
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nPASS: 7 libbz2 groups passed across native, cross, and both mixed builds")


if __name__ == "__main__":
    main()
