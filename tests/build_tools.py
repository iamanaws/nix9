"""Exercise cross-built utilities with the image's command directories hidden."""

import json
from pathlib import Path
import sys
import tarfile
import tempfile

from guest import files_guest


qemu, image, tools, rc, compressed, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    archive = Path(directory, "tools.tar")
    with tarfile.open(archive, "w") as tar:
        def writable(entry):
            entry.mode |= 0o200
            return entry
        tar.add(Path(tools) / "bin", arcname="bin", filter=writable)
        tar.add(rc, arcname="bin/rc", filter=writable)
    fixtures = {"tools.tar": archive, "check.rc": Path(__file__).with_name("build-tools.rc"),
                "input.gz": compressed}
    with files_guest(qemu, image, fixtures) as guest:
        guest.command("mkdir /tmp/build-tools; cd /tmp/build-tools && tar xf /tmp/tools.tar")
        guest.command("workRoot=/tmp/build-tools")
        guest.command("/tmp/build-tools/bin/rc -c 'rfork n; bind /tmp/build-tools/bin /bin; path=(/bin); . /tmp/check.rc /tmp/input.gz'", "build-tools-PASS")
Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "utilities": "file operations, text processing, awk functions and pipes, namespaces, tar and gunzip passed",
}, indent=2) + "\n")
