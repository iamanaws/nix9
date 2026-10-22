"""Check cross-built ar and libmach with real object archives."""

import json
from pathlib import Path
import re
import sys

from guest import files_guest


qemu, image, ar, objects, output = sys.argv[1:]
fixtures = {"ar": ar, **{name: Path(objects) / name for name in ("main.6", "callee.6")}}
with files_guest(qemu, image, fixtures) as guest:
    guest.command("chmod +x /tmp/ar; cd /tmp; SOURCE_DATE_EPOCH=0")
    guest.command("cp callee.6 abcdefghijklmn.6 && /tmp/ar rc library.a abcdefghijklmn.6")
    guest.command("/tmp/ar t library.a", "abcdefghijklmn.6")
    guest.command("6l -o program main.6 library.a && ./program alpha 23", "PASS: varargs and libc calls")
    guest.command("sleep 1; touch abcdefghijklmn.6")
    guest.command("/tmp/ar rc identical.a abcdefghijklmn.6 && cmp library.a identical.a")
    guest.command("rm abcdefghijklmn.6 && /tmp/ar x library.a && cmp callee.6 abcdefghijklmn.6")
    guest.command("/tmp/ar p library.a abcdefghijklmn.6 > printed.6 && cmp callee.6 printed.6")
    guest.command("cp main.6 abcdefghijklmn.6 && /tmp/ar r library.a abcdefghijklmn.6")
    guest.command("rm abcdefghijklmn.6 && /tmp/ar x library.a && cmp main.6 abcdefghijklmn.6")
    guest.command("/tmp/ar d library.a abcdefghijklmn.6")
    result = guest.command("/tmp/ar t library.a")
    if re.search(r"(?m)^abcdefghijklmn\.6$", result):
        raise RuntimeError("ar did not delete the member")
    result = guest.command("SOURCE_DATE_EPOCH=invalid; /tmp/ar rc invalid.a callee.6; echo AR-STATUS:$status")
    if not re.search(r"(?m)^AR-STATUS:.+$", result):
        raise RuntimeError("ar accepted an invalid epoch")
    guest.command("test ! -e invalid.a")
Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "ar": "create, list, link, replace, extract, print, delete, 16-byte member names and timestamps passed",
}, indent=2) + "\n")
