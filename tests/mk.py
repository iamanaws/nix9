"""Check cross-built mk's parsing, regular-expression rules and rc recipes."""

import json
from pathlib import Path
import re
import sys

from guest import files_guest


qemu, image, program, output = sys.argv[1:]
with files_guest(qemu, image, {"mk": program, "mkfile": Path(__file__).with_name("mkfile")}) as guest:
    guest.command("chmod +x /tmp/mk; mkdir /tmp/mk-test; cd /tmp/mk-test")
    guest.command("cp /tmp/mkfile mkfile; echo 'INCLUDED=yes' > included.mk")
    guest.command("echo first > alpha.src; echo second > beta.src")
    guest.command("/tmp/mk -n")
    guest.command("test ! -e alpha.copy")
    guest.command("/tmp/mk")
    guest.command("cat alpha.copy", "first")
    guest.command("cat beta.copy", "second")
    guest.command("rm alpha.copy; /tmp/mk alpha.copy")
    guest.command("cat alpha.copy", "first")
    result = guest.command("/tmp/mk failed; echo MK-STATUS:$status")
    if not re.search(r"(?m)^MK-STATUS:.+", result):
        raise RuntimeError("mk did not propagate recipe failure")
Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "mk": "cross-built mk: includes, regular-expression rules, parallel rc recipes, dry run and failure status passed",
}, indent=2) + "\n")
