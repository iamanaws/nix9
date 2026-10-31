"""Extract a reproducible CPU userland seed from the pinned, unmodified VM."""

import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import shutil
import tarfile
import tempfile
import threading

from artifacts import ArtifactServer
from guest import boot


qemu, image, prototype, output = sys.argv[1:]
destination = Path(output)
destination.mkdir()
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    (work / "root.proto").symlink_to(prototype)
    with ArtifactServer(work, work / "root.tar.gz") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with boot(qemu, image) as guest:
                guest.child.timeout = 600
                guest.command(f"hget -o /tmp/root.proto http://10.0.2.2:{server.server_port}/root.proto")
                guest.command("mkdir /tmp/root; disk/mkfs -d /tmp/root -s /root /tmp/root.proto")
                guest.command("@{ cd /tmp/root && tar cf /tmp/root.tar * }")
                guest.command("gzip -c /tmp/root.tar > /tmp/root.tar.gz")
                guest.command("size=`{ls -l /tmp/root.tar.gz | awk '{print $6}'}")
                guest.command(f"hget -r 'Content-Length: '^$size -P http://10.0.2.2:{server.server_port}/root.tar.gz < /tmp/root.tar.gz")
            if not server.received.is_set():
                raise RuntimeError("VM did not upload the root seed")
        finally:
            server.shutdown()
            thread.join()
    # Sorting entries needs random access; seek in an unpacked tar, not gzip.
    with gzip.open(work / "root.tar.gz", "rb") as packed, (work / "root.tar").open("wb") as raw:
        shutil.copyfileobj(packed, raw)
    with tarfile.open(work / "root.tar", "r:") as source:
        members = {}
        for member in source:
            name = member.name.removeprefix("./").rstrip("/")
            if not name or str(PurePosixPath(name)) != name or name.startswith("/") or ".." in PurePosixPath(name).parts:
                raise RuntimeError(f"unsafe seed path: {name}")
            if name in members or not (member.isdir() or member.isfile()):
                raise RuntimeError(f"unsupported seed entry: {name}")
            if member.isfile() and (name.startswith(("cfg/", "usr/local/", "sys/log/")) or
                    (name.startswith("adm/") and name != "adm/users" and not name.startswith("adm/timezone/"))):
                raise RuntimeError(f"unexpected state in seed: {name}")
            members[name] = member
        for name in ("amd64/init", "amd64/bin/rc", "lib/namespace", "rc/bin/cpurc", "rc/bin/termrc"):
            if name not in members or not members[name].isfile():
                raise RuntimeError(f"incomplete root seed: {name}")
        namespace = source.extractfile(members["lib/namespace"]).read()
        if b". /lib/namespace.local\n" not in namespace:
            raise RuntimeError("seed namespace does not support local includes")
        # VM clock, archive enumeration and filesystem ownership do not affect the seed.
        with (
            (destination / "root.tar.gz").open("wb") as packed,
            gzip.GzipFile(filename="", fileobj=packed, mode="wb", mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT) as archive,
        ):
            for name, member in sorted(members.items()):
                entry = tarfile.TarInfo(name)
                entry.type = tarfile.DIRTYPE if member.isdir() else tarfile.REGTYPE
                entry.mode = member.mode & 0o777
                entry.mtime = 1
                entry.uname = entry.gname = "glenda"
                entry.size = member.size if member.isfile() else 0
                archive.addfile(entry, source.extractfile(member) if member.isfile() else None)
    with Path(image).open("rb") as source:
        image_hash = hashlib.file_digest(source, "sha256").hexdigest()
    (destination / "base.json").write_text(json.dumps({
        "release": "9front-11952-amd64", "imageSha256": image_hash, "format": "tar.gz",
    }, sort_keys=True) + "\n")
