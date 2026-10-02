"""Usage: python tests/sqlite.py QEMU DISK cc9-amd64.tar.gz sqlite-amalgamation-3510200.zip

SQLite source: https://www.sqlite.org/2026/sqlite-amalgamation-3510200.zip
"""

import hashlib
from pathlib import Path
import sys
import subprocess
import tempfile
import zipfile

from cxx import cc9_guest


qemu, disk, cc9, archive = sys.argv[1:]
digest = "6e2a845a493026bdbad0618b2b5a0cf48584faab47384480ed9f592d912f23ec"
with open(archive, "rb") as source:
    if hashlib.file_digest(source, "sha256").hexdigest() != digest:
        raise SystemExit("expected SQLite 3.51.2 amalgamation")

with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(archive) as source:
    files = {}
    for name in ("sqlite3.c", "sqlite3.h"):
        files[name] = Path(directory) / name
        files[name].write_bytes(source.read(f"sqlite-amalgamation-3510200/{name}"))
    port = Path(__file__).resolve().parents[1] / "pkgs" / "cc9-libs"
    subprocess.run(["patch", "-d", directory, "-p1", "-i", str(port / "sqlite.patch")], check=True)
    files["plan9-lock.c"] = port / "plan9-lock.c"
    for name in ("build.rc", "probe.cpp"):
        files[name] = Path(__file__).parent / "sqlite" / name
    with cc9_guest(qemu, disk, cc9, files) as guest:
        guest.command("rc /tmp/build.rc")
        guest.command("/tmp/sqlite-probe unix-dotfile", "sqlite unix-dotfile probe PASS")
        guest.command("/tmp/sqlite-probe unix-plan9", "sqlite unix-plan9 probe PASS")
