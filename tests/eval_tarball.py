"""Compare fetched archive trees with host Nix hashes and test unsafe members."""

import io
import random
import re
import subprocess
import tarfile


def tree_hash(path):
    return subprocess.check_output([
        "nix", "--extra-experimental-features", "nix-command", "hash", "path", "--sri", str(path),
    ], text=True).strip()


def check_eval_tarball(guest, root, base, secure):
    tree = root / "archive-tree"
    (tree / "lib").mkdir(parents=True)
    (tree / "bin").mkdir()
    (tree / "empty").mkdir()
    (tree / "default.nix").write_text("import ./lib/answer.nix\n")
    (tree / "lib/answer.nix").write_text("42\n")
    (tree / "bin/hello").write_text("#!/bin/rc\necho archive-PASS\n")
    (tree / "bin/hello").chmod(0o755)
    digest = tree_hash(tree)
    for suffix, mode in (("tar", "w"), ("tar.gz", "w:gz"), ("tar.xz", "w:xz")):
        with tarfile.open(root / f"project.{suffix}", mode) as archive:
            archive.add(tree, arcname="project-v1")
    with tarfile.open(root / "flat.tar", "w") as archive:
        for entry in sorted(tree.iterdir()):
            archive.add(entry, arcname=entry.name)
    with tarfile.open(root / "implicit.tar", "w") as archive:
        for entry in sorted(tree.rglob("*")):
            if entry.is_file() or entry.name == "empty":
                archive.add(entry, arcname="project-v1/" + str(entry.relative_to(tree)))
        archive.add(tree / "lib", arcname="project-v1/lib", recursive=False)
        archive.add(tree / "lib", arcname="project-v1/lib", recursive=False)
    for name, directory_first in (("file-directory", False), ("directory-file", True)):
        with tarfile.open(root / f"{name}.tar", "w") as archive:
            for directory in (directory_first, not directory_first):
                entry = tarfile.TarInfo("project-v1/item")
                entry.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
                archive.addfile(entry)
    empty = root / "empty-tree"
    empty.mkdir()
    with tarfile.open(root / "empty.tar", "w"):
        pass
    for name, kind in (("symlink", tarfile.SYMTYPE), ("hardlink", tarfile.LNKTYPE),
                       ("fifo", tarfile.FIFOTYPE), ("duplicate", tarfile.REGTYPE)):
        with tarfile.open(root / f"{name}.tar", "w") as archive:
            archive.add(tree, arcname="project-v1")
            entry = tarfile.TarInfo("project-v1/lib/answer.nix" if name == "duplicate" else "project-v1/link")
            entry.type = kind
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                entry.linkname = "project-v1/lib/answer.nix" if name == "hardlink" else "/tmp/nix9-archive-outside"
            archive.addfile(entry)
    (root / "corrupt.tar").write_bytes(b"not an archive")
    data = (root / "project.tar.gz").read_bytes()
    (root / "truncated.tar.gz").write_bytes(data[:len(data) // 2])
    normalized = root / "normalized-tree"
    normalized.mkdir()
    (normalized / "nix9-archive-outside").write_bytes(b"inside")
    for name, member in (("parent", "../../tmp/nix9-archive-outside"),
                         ("absolute", "/tmp/nix9-archive-outside")):
        with tarfile.open(root / f"{name}.tar", "w") as archive:
            entry = tarfile.TarInfo(member)
            entry.size = 6
            archive.addfile(entry, io.BytesIO(b"inside"))
    (root / "eval-tarball.nix").write_text('''
      { url, hash, name ? "source" }:
      let path = builtins.fetchTarball { inherit url name; sha256 = hash; };
      in { inherit path; answer = import path; }
    ''')
    guest.command(f"hget -o /tmp/eval-tarball.nix {base}/eval-tarball.nix")
    guest.command("mkdir /tmp/nix9-archive-temp")
    guest.command("fn evalTarball { TMPDIR=/tmp/nix9-archive-temp nix-instantiate --eval --strict --json --argstr url $tarballUrl --argstr hash $tarballHash /tmp/eval-tarball.nix $* }")
    guest.command(f"tarballHash='{digest}'; tarballUrl={base}/project.tar.gz")
    result = guest.command("evalTarball -A path")
    paths = re.findall(r'(?m)^"(/usr/local/nix/store/[^"\n]+)"$', result)
    if len(paths) != 1:
        raise RuntimeError(f"missing archive fetch output: {result}")
    path = paths[0]
    guest.command(f"tarballTree={path}")
    guest.command("nix-store --realise --add-root /usr/local/nix/state/gcroots/eval-tree $tarballTree")
    guest.command("evalTarball -A answer", "42")
    guest.command("$tarballTree/bin/hello", "archive-PASS")
    for url, name in ((base + "/project.tar", "plain-tree"), (base + "/project.tar.xz", "xz-tree"),
                      (base + "/flat.tar", "flat-tree"), (base + "/implicit.tar", "implicit-tree"),
                      (secure + "/project.tar.gz", "https-tree")):
        guest.command(f"tarballUrl={url}")
        guest.command(f"evalTarball --argstr name {name} -A answer", "42")
        check_archive_cleanup(guest)
    guest.command("echo untouched > /tmp/nix9-archive-outside")
    for archive, reason in (("symlink.tar", "symbolic links"), ("hardlink.tar", "hard links"),
                            ("fifo.tar", "unsupported file type"), ("duplicate.tar", "duplicate archive member"),
                            ("file-directory.tar", "creating directory"), ("directory-file.tar", "duplicate archive member"),
                            ("corrupt.tar", "archive"), ("truncated.tar.gz", "")):
        guest.command(f"tarballUrl={base}/{archive}")
        result = guest.command("evalTarball --argstr name rejected-tree -A path; echo ARCHIVE-ERROR:$status")
        if reason not in result or not re.search(r"(?m)^ARCHIVE-ERROR:.+$", result):
            raise RuntimeError(f"archive fetch accepted {archive}: {result}")
        guest.command("cat /tmp/nix9-archive-outside", "untouched")
        check_archive_cleanup(guest)
    guest.command(f"tarballHash='{tree_hash(empty)}'; tarballUrl={base}/empty.tar")
    guest.command("evalTarball --argstr name empty-tree -A path")
    check_archive_cleanup(guest)
    guest.command(f"tarballHash='{tree_hash(normalized)}'")
    for name in ("parent", "absolute"):
        guest.command(f"tarballUrl={base}/{name}.tar")
        guest.command(f"evalTarball --argstr name {name}-tree -A path")
        guest.command("cat /tmp/nix9-archive-outside", "untouched")
    guest.command(f"tarballUrl={base}/project.tar.gz")
    guest.command("tarballHash='sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='")
    result = guest.command("evalTarball --argstr name wrong-tree -A path; echo ARCHIVE-ERROR:$status")
    if "hash mismatch" not in result or not re.search(r"(?m)^ARCHIVE-ERROR:.+$", result):
        raise RuntimeError(f"archive fetch accepted a wrong hash: {result}")
    check_archive_cleanup(guest)
    guest.command(f"tarballHash='{digest}'")
    guest.command("pureTarballExpr='{url, hash}: import (builtins.fetchTarball {inherit url; sha256=hash;})'")
    guest.command("fn pureTarball { nix-instantiate --eval --json --pure-eval --argstr url $tarballUrl --argstr hash $tarballHash --expr $pureTarballExpr }")


def check_archive_cleanup(guest):
    guest.command("test `{ls /tmp/nix9-archive-temp | wc -l} -eq 0")


def check_large_tarball(guest, root, base):
    # Larger than the test VM's RAM, with enough incompressible data to exercise
    # both the download and extraction paths. Write the fixture in small chunks.
    tree = root / "large-tree"
    tree.mkdir()
    (tree / "default.nix").write_text("42\n")
    size = 640 * 1024 * 1024
    rng = random.Random(0)
    with (tree / "payload").open("wb") as payload:
        for _ in range(128):
            payload.write(rng.randbytes(1024 * 1024))
        payload.truncate(size)
    with tarfile.open(root / "large.tar.gz", "w:gz", compresslevel=1) as archive:
        archive.add(tree, arcname="project-v1")
    guest.command(f"tarballHash='{tree_hash(tree)}'; tarballUrl={base}/large.tar.gz")
    result = guest.command("evalTarball --argstr name large-tree -A path")
    paths = re.findall(r'(?m)^"(/usr/local/nix/store/[^"\n]+)"$', result)
    if len(paths) != 1:
        raise RuntimeError(f"missing large archive output: {result}")
    path = paths[0]
    guest.command(f"nix-instantiate --eval {path}", "42")
    guest.command(f"test `{{wc -c < {path}/payload}} -eq {size}")
    guest.command(f"nix-store --verify-path {path}")
    check_archive_cleanup(guest)
    # Leave the original fixture selected for the offline reuse tests.
    guest.command(f"tarballHash='{tree_hash(root / 'archive-tree')}'; tarballUrl={base}/project.tar.gz")
