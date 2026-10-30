"""Native archive errors, metadata and SHA-256 using the cross-built tools."""

import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

from guest import files_guest


qemu, image, package, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    binaries = {name: Path(package) / "bin/disk" / name for name in ("mkfs", "mkext", "checksum")}
    with files_guest(qemu, image, binaries) as guest:
        guest.command("chmod 755 /tmp/mkfs /tmp/mkext /tmp/checksum")

        def rejected(command, reason):
            result = guest.command("rc -c '" + command.replace("'", "''") + "'; echo ARCHIVE-ERROR:$status")
            if not re.search(r"(?m)^ARCHIVE-ERROR:.+", result) or reason.lower() not in result.lower():
                raise RuntimeError(f"archive error was not reported: {command}: {result}")

        guest.command("mkdir /tmp/source /tmp/destination; mkdir /tmp/source/projects")
        guest.command("echo payload > '/tmp/source/projects/a file'; echo -n > /tmp/source/projects/empty")
        guest.command("chmod 640 '/tmp/source/projects/a file'")
        guest.command("echo 'projects - - -' > /tmp/proto; echo ' + - - -' >> /tmp/proto")
        guest.command("/tmp/mkfs -a -s /tmp/source /tmp/proto > /tmp/archive")
        guest.command("/tmp/mkext -h < /tmp/archive > /tmp/headers")
        guest.command("/tmp/mkext -u -d /tmp/destination < /tmp/archive")
        guest.command("cmp '/tmp/source/projects/a file' '/tmp/destination/projects/a file'")
        guest.command("test ! -s /tmp/destination/projects/empty")
        guest.command("ls -l '/tmp/destination/projects/a file' | awk '{print $1}'", "--rw-r-----")
        guest.command("/tmp/checksum /tmp/source/projects/empty", hashlib.sha256(b"").hexdigest())
        guest.command("/tmp/checksum '/tmp/source/projects/a file'", hashlib.sha256(b"payload\n").hexdigest())
        guest.command("/tmp/checksum /tmp/archive > /tmp/hash; /tmp/checksum -c /tmp/hash /tmp/archive")
        guest.command("echo changed >> /tmp/archive")
        rejected("/tmp/checksum -c /tmp/hash /tmp/archive", "mismatch")
        guest.command("echo '/projects/file 640 glenda glenda 1 8' > /tmp/bad; echo -n short >> /tmp/bad")
        rejected("/tmp/mkext -h < /tmp/bad", "premature eof")
        guest.command("echo '/projects/../outside 640 glenda glenda 1 0' > /tmp/bad; echo 'end of archive' >> /tmp/bad")
        rejected("/tmp/mkext -d /tmp/destination < /tmp/bad", "noncanonical archive path")
        guest.command("test ! -e /tmp/outside")
        guest.command("echo 'missing - - -' > /tmp/missing-proto")
        rejected("/tmp/mkfs -a -s /tmp/source /tmp/missing-proto > /tmp/missing-archive", "can't stat file")
        rejected("/tmp/mkext -h < /tmp/missing-archive", "premature end of archive")
        print("PASS: Plan 9 archive round trip, metadata, SHA-256 vectors, corruption, truncation, traversal and missing-file failure", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({"status": "passed", "checks": [
        "round-trip", "metadata", "quoted-names", "empty-files", "sha256-vectors", "checksum-mismatch",
        "truncated-payload", "path-traversal", "missing-source-failure"]}, indent=2) + "\n")
