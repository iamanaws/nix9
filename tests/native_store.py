"""Check transfers and caches using an exported native package closure."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from native_transfer import check_transfer


qemu, image, archive, prefix, fixture, probe, elf2aout, output = sys.argv[1:]
fixture = Path(fixture)
sources = json.loads((fixture / "info.json").read_text())
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for name in ("closure.export", "cert.pem", "key.pem"):
        shutil.copyfile(fixture / name, root / name)
    subprocess.run([sys.executable, elf2aout, probe, str(root / "store-probe")], check=True)
    result = check_transfer(qemu, image, root, archive, prefix, sources, set(sources["paths"]))
Path(output, "native-store.json").write_text(json.dumps(result, indent=2) + "\n")
print("PASS: closure transfer, signed caches, repair, recovery and network substitution")
