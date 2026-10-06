"""Check the native upstream CLI against host Nix's store paths and NARs."""

import hashlib
import re
import subprocess


def check_nix_store(guest, fixtures):
    guest.command("/tmp/nix-store --help", "Usage: nix-store [--store URI] OPERATION [ARGS...]")
    guest.command("/tmp/nix-store --version", "nix-store (Nix) 2.34.8")
    cli = "/tmp/nix-store --store /tmp/nix9-cli"
    guest.command(f"{cli} --init")
    paths, hashes = [], []
    for name, fixture in (("cli-file", "file"), ("cli-tree", "import")):
        nar = fixtures[fixture]
        digest = hashlib.sha256(nar).hexdigest()
        path = subprocess.check_output([
            "nix-store", "--store", "dummy://", "--print-fixed-path", "--recursive", "sha256", digest, name,
        ], text=True).strip()
        nix32 = subprocess.check_output([
            "nix", "--extra-experimental-features", "nix-command", "hash", "convert",
            "--hash-algo", "sha256", "--from", "base16", "--to", "nix32", digest,
        ], text=True).strip()
        guest.command(f"/tmp/nix-store --restore /tmp/{name} < /tmp/{fixture}.nar")
        guest.command(f"{cli} --add /tmp/{name}", path)
        guest.command(f"{cli} --add /tmp/{name}", path)
        guest.command(f"{cli} --check-validity {path}")
        guest.command(f"{cli} --query --hash {path}", f"sha256:{nix32}")
        guest.command(f"{cli} --query --size {path}", str(len(nar)))
        guest.command(f"{cli} --query --requisites {path}", path)
        guest.command(f"{cli} --query --references {path} > /tmp/refs && test ! -s /tmp/refs")
        guest.command(f"{cli} --verify-path {path}")
        guest.command(f"/tmp/nix-store --dump /tmp/nix9-cli{path} > /tmp/cli.nar")
        guest.command(f"cmp /tmp/{fixture}.nar /tmp/cli.nar")
        paths.append(path)
        hashes.append(nix32)

    # Each invocation reopens the database; rc can pass the same store via /env.
    guest.command(f"NIX_REMOTE=/tmp/nix9-cli /tmp/nix-store -q --hash {paths[0]}",
                  "sha256:" + hashes[0])
    guest.command(f"echo {paths[0]} | {cli} --query --size --stdin", str(len(fixtures["file"])))

    for args, message in (
        ("", "no operation specified"),
        ("--add --query", "only one operation may be specified"),
        ("--query --bogus", "unknown flag"),
        ("--add /tmp/missing-cli-input", "does not exist"),
        ("--query --hash /nix/store/00000000000000000000000000000000-missing", "not valid"),
        ("--serve", "not supported"),
        ("--log-format bar --init", "not supported"),
    ):
        output = guest.command(f"{cli} {args}; echo CLI-STATUS:$status")
        if not re.search(r"(?m)^CLI-STATUS:.*cc9exit=1$", output) or message not in output:
            raise RuntimeError(f"expected CLI failure ({message}): {args}\n{output}")

    guest.command("ls /tmp/nix9-cli/nix/var/nix/temproots > /tmp/roots && test ! -s /tmp/roots")
    guest.command(f"{cli} --check-validity {' '.join(paths)}")
    guest.command(f"{cli} --realise {paths[0]}", paths[0])
    return ["add", "query", "host store paths", "NAR round-trip", "reopen",
            "environment", "stdin", "error status", "temporary-root cleanup"]
