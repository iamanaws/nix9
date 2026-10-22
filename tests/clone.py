"""Run the same file-copy checks against native and cross-built clone."""

import json
from pathlib import Path
import re
import sys
import tempfile

from guest import files_guest


def copy_fixtures(directory):
    payload = Path(directory) / "payload"
    payload.write_bytes(bytes(range(256)) * 2048)
    return {"payload": payload, "copy.rc": Path(__file__).with_suffix(".rc")}


def check_copy(guest, program, session):
    namespace = guest.command("cat /proc/$pid/ns")
    guest.command(f"{session} rc /tmp/copy.rc {program}", "upstream-clone-PASS")
    guest.command("test ! -f /mnt/destination/payload")
    if guest.command("cat /proc/$pid/ns") != namespace:
        raise RuntimeError("copy session changed its parent's namespace")
    guest.command(f"{program} /tmp/payload /tmp/copied")
    guest.command("cmp /tmp/payload /tmp/copied")
    guest.command("mkdir -p /tmp/tree/nested; echo persistent > /tmp/tree/nested/message")
    guest.command(f"{program} /tmp/tree /tmp/copied-tree")
    guest.command("cmp /tmp/tree/nested/message /tmp/copied-tree/nested/message")
    result = guest.command(f"{session} {program} /tmp/nonexistent /mnt/missing; echo COPY-STATUS:$status")
    if not re.search(r"(?m)^COPY-STATUS:.+", result):
        raise RuntimeError("clone did not report a missing source")


def main():
    qemu, image, program, output = sys.argv[1:]
    with tempfile.TemporaryDirectory() as directory:
        session = Path(directory) / "session"
        session.write_text("#!/bin/rc -e\nrfork ne\nramfs -m /mnt\nexec $*\n")
        fixtures = copy_fixtures(directory) | {"clone": program, "session": session}
        with files_guest(qemu, image, fixtures) as guest:
            guest.command("chmod +x /tmp/clone /tmp/session")
            check_copy(guest, "/tmp/clone", "/tmp/session")
    Path(output).mkdir()
    Path(output, "results.json").write_text(json.dumps({
        "clone": "cross-built binary: parallel copies, empty files, overwrite, directories, namespaces and failure status passed",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
