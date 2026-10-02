"""Usage: python tests/nar.py QEMU DISK cc9-amd64.tar.gz

Uses host nix-store as an independent NAR oracle. No store paths are imported.
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from artifacts import ArtifactServer
from cxx import cc9_guest


def dump(path):
    return subprocess.check_output(["nix-store", "--dump", str(path)])


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    plain = root / "plain"
    plain.mkdir()
    (plain / "empty").mkdir()
    (plain / "binary").write_bytes(bytes(range(256)) * 7 + b"\0tail")
    (plain / "run").write_text("#!/bin/rc\necho native\n")
    (plain / "run").chmod(0o755)
    (plain / "zero").touch()
    (plain / ".nix9-links").write_text("ordinary filename, not metadata")
    (plain / "space and unicode-λ").write_text("names are bytes")
    names = root / "names"
    names.mkdir()
    (names / "name\nwith newline").write_text("preserve in NAR only")
    (names / "name\x7fwith DEL").touch()

    links = root / "links"
    links.mkdir()
    (links / "file").write_text("content")
    (links / "directory").mkdir()
    targets = {
        "relative": "file", "absolute": "/nix/store/example/bin/tool",
        "dangling": "missing", "parent": "../outside", "directory-link": "directory",
        "cycle-a": "cycle-b", "cycle-b": "cycle-a", "self": "self",
        "newline": "missing\ntarget",
    }
    for name, target in targets.items():
        (links / name).symlink_to(target)
    (root / "root-link").symlink_to("missing-root")
    cases = {"plain": plain, "links": links, "names": names,
             "file": plain / "binary", "link": root / "root-link"}
    files = {"probe.cpp": Path(__file__).parent / "nar/probe.cpp"}
    originals = {}
    for name, path in cases.items():
        originals[name] = dump(path)
        files[f"{name}.nar"] = root / f"{name}.nar"
        files[f"{name}.nar"].write_bytes(originals[name])

    # Invalid lengths, padding, names, truncation and trailing input must fail
    # before an extraction destination appears.
    bad = {
        "truncated": originals["plain"][:-1],
        "trailing": originals["plain"] + b"x",
        "length": b"\xff" * 8,
        "padding": originals["file"][:21] + b"x" + originals["file"][22:],
        "traversal": originals["plain"].replace(b"name\0\0\0\0\x06\0\0\0\0\0\0\0binary",
                                                 b"name\0\0\0\0\x06\0\0\0\0\0\0\0../bad"),
    }
    assert bad["traversal"] != originals["plain"]
    for name, data in bad.items():
        files[f"{name}.nar"] = root / f"{name}.nar"
        files[f"{name}.nar"].write_bytes(data)

    returned = root / "returned.nar"
    with ArtifactServer(directory, returned) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with cc9_guest(*sys.argv[1:], files) as guest:
                guest.command("/amd64/bin/cc /tmp/probe.cpp -o /tmp/nar-probe")
                for name in cases:
                    guest.command(f"/tmp/nar-probe roundtrip /tmp/{name}.nar /tmp/{name}.out.nar",
                                  "nar roundtrip PASS")
                for name in ("plain", "file"):
                    guest.command(f"/tmp/nar-probe extract /tmp/{name}.nar /tmp/{name}.tree",
                                  "nar extract PASS")
                    guest.command(f"/tmp/nar-probe dump /tmp/{name}.tree /tmp/{name}.disk.nar",
                                  "nar dump PASS")
                for name in ("links", "link", "names", *bad):
                    guest.command(
                        f"if(/tmp/nar-probe extract /tmp/{name}.nar /tmp/{name}.rejected) "
                        "{echo unexpected-success}; if not {echo rejected}", "rejected")
                    guest.command(f"if(test -e /tmp/{name}.rejected) {{echo unexpected-output}}; "
                                  "if not {echo no-output}", "no-output")

                for name in (*cases, "plain.disk", "file.disk"):
                    guest_path = f"/tmp/{name}.out.nar" if name in cases else f"/tmp/{name}.nar"
                    server.received.clear()
                    guest.command(
                        f"size=`{{ls -l {guest_path} | awk '{{print $6}}'}}; "
                        f"hget -r 'Content-Length: '^$size -P "
                        f"http://10.0.2.2:{server.server_port}/returned.nar <{guest_path}")
                    if not server.received.is_set():
                        raise RuntimeError("missing returned NAR")
                    assert returned.read_bytes() == originals[name.split(".")[0]], name
                    restored = root / f"restored-{name}"
                    subprocess.run(["nix-store", "--restore", str(restored)],
                                   input=returned.read_bytes(), check=True)
                    assert dump(restored) == returned.read_bytes(), name
                    if name == "links":
                        assert all((restored / key).readlink() == Path(value)
                                   for key, value in targets.items())
        finally:
            server.shutdown()
            thread.join()
    print("PASS: Nix NAR round trips, filesystem extraction, symlinks, and rejection checks")
