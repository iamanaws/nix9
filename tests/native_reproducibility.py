"""Compare native toolchain rebuilds in two fresh VMs, without substitutions."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import threading

from artifacts import ArtifactServer
from guest import boot


def archive_dates(path):
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise RuntimeError(f"not an archive: {path}")
    offset = 8
    dates = []
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise RuntimeError(f"invalid archive member: {path}")
        dates.append(int(header[16:28]))
        size = int(header[48:58])
        offset += 60 + size + size % 2
    if offset != len(data) or len(dates) < 2:
        raise RuntimeError(f"missing archive members or symbol table: {path}")
    return dates


qemu, image, nix_archive, nix_prefix, packages_archive, packages, output = sys.argv[1:]
names = ("ar", "cc", "libc", "libbio", "libregexp", "mk", "rc")
runs = []
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    for run in range(2):
        root = work / str(run)
        root.mkdir()
        for name, source in (("nix.tar", nix_archive), ("packages.tar", packages_archive),
                             ("reproducibility.nix", Path(__file__).with_name("reproducibility.nix"))):
            (root / name).symlink_to(Path(source).resolve())
        with ArtifactServer(root, root / "outputs.tar") as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with boot(qemu, image) as guest:
                    guest.child.timeout = 600
                    for name in ("nix.tar", "packages.tar", "reproducibility.nix"):
                        guest.command(f"hget -o /tmp/{name} http://10.0.2.2:{server.server_port}/{name}")
                    guest.command("cd / && tar xf /tmp/nix.tar && tar xf /tmp/packages.tar")
                    guest.command(f". {nix_prefix}/activate; NIX_CONFIG='substituters ='")
                    guest.command("mkdir /tmp/outputs; roots=/usr/local/nix/state/gcroots")
                    guest.command("nix-instantiate --eval --expr builtins.currentTime > /tmp/outputs/time")
                    for name in names:
                        result = guest.command(f"nix-build {packages} -A {name} --out-link $roots/{name}")
                        if "copying path" in result:
                            raise RuntimeError(f"{name} was substituted during a rebuild")
                        if run == 0:
                            guest.command(f"nix-build {packages} -A {name} --check --no-out-link")
                        guest.command(f"cat $roots/{name} > /tmp/outputs/{name}.path")
                        guest.command(f"p=`{{cat $roots/{name}}}; nix-store --dump $p > /tmp/outputs/{name}.nar")
                    guest.command(f"nix-build /tmp/reproducibility.nix --argstr packages {packages} --out-link $roots/epochs")
                    guest.command("ar=`{cat $roots/ar}^/bin/ar")
                    result = guest.command("@{ SOURCE_DATE_EPOCH=invalid; $ar rc /tmp/invalid.a }; echo AR-STATUS:$status")
                    if not re.search(r"(?m)^AR-STATUS:.+", result):
                        raise RuntimeError("ar accepted an invalid epoch")
                    guest.command("test ! -e /tmp/invalid.a")
                    guest.command("p=`{cat $roots/epochs}; nix-store --dump $p > /tmp/outputs/epochs.nar")
                    guest.command("cd /tmp/outputs && tar cf /tmp/outputs.tar *")
                    guest.command("size=`{ls -l /tmp/outputs.tar | awk '{print $6}'}")
                    guest.command(f"hget -r 'Content-Length: '^$size -P http://10.0.2.2:{server.server_port}/outputs.tar < /tmp/outputs.tar")
                if not server.received.is_set():
                    raise RuntimeError("VM did not upload the rebuilt outputs")
            finally:
                server.shutdown()
                thread.join()
        with tarfile.open(root / "outputs.tar") as archive:
            archive.extractall(root, filter="data")
        with (root / "epochs.nar").open("rb") as source:
            subprocess.run(["nix-store", "--restore", str(root / "epochs")], stdin=source, check=True)
        for name, expected in (("zero", 0), ("custom", 42)):
            if any(date != expected for date in archive_dates(root / "epochs" / (name + ".a"))):
                raise RuntimeError(f"ar did not use the {name} epoch for every member")
        if any(date <= 42 for date in archive_dates(root / "epochs/ordinary.a")):
            raise RuntimeError("ar changed timestamps without SOURCE_DATE_EPOCH")
        runs.append(root)
    if (runs[0] / "time").read_bytes() == (runs[1] / "time").read_bytes():
        raise RuntimeError("rebuilds did not run at different times")
    results = {}
    for name in names:
        paths = [(root / (name + ".path")).read_text().strip() for root in runs]
        hashes = [hashlib.sha256((root / (name + ".nar")).read_bytes()).hexdigest() for root in runs]
        if paths[0] != paths[1] or hashes[0] != hashes[1]:
            raise RuntimeError(f"{name} is not reproducible: {paths}, {hashes}")
        results[name] = {"output": paths[0], "nar-sha256": hashes[0]}

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps(results, indent=2) + "\n")
print("PASS: native toolchain rebuilds have identical paths and NAR hashes")
