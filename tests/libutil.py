"""Exercise upstream Nix's libutil on 9front, using host Nix as the oracle.

Usage: python tests/libutil.py QEMU DISK CC9_ARCHIVE PROBE_ELF NIX_STORE_ELF NIX_EVAL_ELF OUTPUT
"""

import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from cxx import cc9_guest
from nix_store import check_nix_store
from nix_eval import eval_fixtures, check_nix_eval
from libutil_compression import check_compression
from libutil_keys import key_fixtures, check_keys


qemu, disk, cc9, executable, nix_store, nix_eval, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    tree = root / "tree"
    tree.mkdir()
    (tree / "binary").write_bytes(bytes(range(256)) + b"\0tail")
    (tree / "executable").write_text("#!/bin/rc\necho test\n")
    (tree / "executable").chmod(0o755)
    (tree / "empty").mkdir()
    (tree / "newline\nname").touch()
    for name, target in {"relative": "binary", "absolute": "/missing",
                         "dangling": "missing", "cycle": "cycle"}.items():
        (tree / name).symlink_to(target)
    fixtures = {}
    for name, path in {"tree": tree, "file": tree / "binary", "link": tree / "dangling"}.items():
        fixtures[name] = subprocess.check_output(["nix-store", "--dump", str(path)])
    store_tree = root / "store-tree"
    (store_tree / "empty").mkdir(parents=True)
    (store_tree / "binary").write_bytes((tree / "binary").read_bytes())
    (store_tree / "executable").write_text("#!/bin/rc\necho imported\n")
    (store_tree / "executable").chmod(0o755)
    fixtures["import"] = subprocess.check_output(["nix-store", "--dump", str(store_tree)])
    fixtures.update({
        "truncated": fixtures["tree"][:-1],
        "trailing": fixtures["file"] + b"x",
        "length": b"\xff" * 8,
        "padding": fixtures["file"][:21] + b"x" + fixtures["file"][22:],
        "traversal": fixtures["tree"].replace(b"binary", b"../bad"),
    })
    files = {"probe.elf": executable, "nix-store.elf": nix_store, "nix-eval.elf": nix_eval}
    files.update(key_fixtures(root))
    files.update(eval_fixtures(root))
    for name, data in fixtures.items():
        path = root / f"{name}.nar"
        path.write_bytes(data)
        files[path.name] = path
    # Exercise digest padding boundaries, BLAKE3 tree chunks, and larger streams.
    sizes = (0, 1, 55, 56, 63, 64, 65, 111, 112, 127, 128, 129, 1023, 1024, 1025, 65537, 131073)
    algorithms = ("md5", "sha1", "sha256", "sha512", "blake3")
    payload = (bytes(range(256)) * 513)[:max(sizes)]
    hash_input, manifest = root / "hash-input", root / "hash-cases"
    prefix = root / "prefix"
    cases = []
    nix = ["nix", "--extra-experimental-features", "nix-command blake3-hashes"]
    for size in sizes:
        prefix.write_bytes(payload[:size])
        for algorithm in algorithms:
            hex_hash = subprocess.check_output(
                nix + ["hash", "file", "--type", algorithm, "--base16", str(prefix)], text=True).strip()
            nix32 = subprocess.check_output(
                nix + ["hash", "convert", "--hash-algo", algorithm,
                       "--from", "base16", "--to", "nix32", hex_hash], text=True).strip()
            b64 = base64.b64encode(bytes.fromhex(hex_hash)).decode()
            cases.append(f"{size} {algorithm} {hex_hash} {nix32} {b64} {algorithm}-{b64}")
    hash_input.write_bytes(payload)
    manifest.write_text(str(len(cases)) + "\n" + "\n".join(cases) + "\n")
    files.update({"hash-input": hash_input, "hash-cases": manifest})
    with cc9_guest(qemu, disk, cc9, files) as guest:
        guest.command("elf2aout /tmp/probe.elf /tmp/libutil-probe && chmod +x /tmp/libutil-probe")
        cli = check_nix_store(guest, fixtures)
        evaluator = check_nix_eval(guest)
        guest.command("mkdir -p /tmp/nix9-process-dir")
        guest.command("/tmp/libutil-probe sqlite", "libstore SQLite PASS")
        guest.command("/tmp/libutil-probe store", "libstore LocalStore PASS")
        guest.command("/tmp/libutil-probe processes", "libutil processes PASS")
        guest.command("/tmp/libutil-probe urls", "libutil URLs PASS")
        signatures = check_keys(guest, root)
        guest.command("/tmp/libutil-probe unsupported", "unsupported features reject PASS")
        guest.command("/tmp/libutil-probe coroutines", "libutil coroutines PASS")
        guest.command("/tmp/libutil-probe hashes /tmp/hash-input /tmp/hash-cases", "libutil hashes PASS")
        compression = check_compression(guest, root)
        for name in ("tree", "file", "link"):
            guest.command(f"/tmp/libutil-probe /tmp/{name}.nar /tmp/{name}.out", "libutil archive PASS")
            guest.command(f"cmp /tmp/{name}.nar /tmp/{name}.out")
        for name in ("truncated", "trailing", "length", "padding", "traversal"):
            guest.command(
                f"if(/tmp/libutil-probe /tmp/{name}.nar /tmp/{name}.out) "
                "{echo unexpected-success}; if not {echo rejected}", "rejected")
            guest.command(f"if(test -e /tmp/{name}.out) {{echo unexpected-output}}; "
                          "if not {echo no-output}", "no-output")
    Path(output).mkdir()
    (Path(output) / "results.json").write_text(json.dumps({
        "nix": "2.34.8", "valid_archives": 3, "rejected_archives": 5,
        "coroutines": ["streaming", "finish", "cancellation", "exceptions"],
        "hash_algorithms": algorithms, "hash_cases": len(cases),
        "compression": compression,
        "nix_store": cli,
        "evaluator": evaluator,
        "urls": ["parsing", "encoding", "relative resolution", "invalid input"],
        "signatures": signatures,
        "processes": ["pipes", "exit status", "PATH", "environment", "working directory",
                      "close-on-exec", "wait", "kill", "interrupt/hangup", "cancellation cleanup"],
        "sqlite": ["store schema", "bindings", "transactions", "foreign keys", "busy retry",
                   "killed-writer recovery", "40 competing commits", "file replacement",
                   "immutable reads", "rollback journal cache"],
        "local_store": ["registration", "metadata", "references", "closure", "rollback",
                        "reopen", "exclusive access", "killed-client recovery", "temporary roots",
                        "NAR imports", "streaming imports", "permissions", "failed-import cleanup"],
        "path_locks": ["contention", "blocking wait", "partial rollback", "cleanup",
                       "killed holder", "fork inheritance", "close-on-exec"],
        "unsupported_features": ["signal handler thread", "pseudoterminals", "file locks",
                                 "process credentials", "process groups", "user termination"],
    }, indent=2) + "\n")
