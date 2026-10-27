"""Use upstream signed file caches to substitute a native package closure."""

import lzma
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from cache_publish import publish_cache


def cache_fixture(root):
    secret, public = root / "cache.key", root / "cache.pub"
    subprocess.run(["nix-store", "--store", "dummy://", "--generate-binary-cache-key",
                    "nix9-test", str(secret), str(public)], check=True)
    uri = f"file://{root}/cache?store=/usr/local/nix/store&secret-key={secret}&compression=xz"
    with (root / "closure.export").open("rb") as source:
        subprocess.run(["nix-store", "--store", uri, "--import"], stdin=source,
                       stdout=subprocess.DEVNULL, check=True)
    for variant in ("bad-signature", "bad-content"):
        cache = root / variant
        shutil.copytree(root / "cache", cache)
        if variant == "bad-signature":
            for info in cache.glob("*.narinfo"):
                text = info.read_text()
                signature = re.search(r"(?m)^Sig: nix9-test:(.)", text)
                if not signature:
                    raise RuntimeError("host cache is unsigned")
                index = signature.start(1)
                text = text[:index] + ("A" if text[index] != "A" else "B") + text[index + 1:]
                info.write_text(text)
        else:
            for nar in (cache / "nar").glob("*.xz"):
                with tempfile.TemporaryDirectory() as directory:
                    tree = Path(directory) / "nar"
                    subprocess.run(["nix-store", "--restore", str(tree)],
                                   input=lzma.decompress(nar.read_bytes()), check=True)
                    files = [tree] if tree.is_file() else tree.rglob("*")
                    target = next(path for path in files if path.is_file() and path.stat().st_size)
                    target.chmod(target.stat().st_mode | 0o200)
                    with target.open("r+b") as contents:
                        byte = contents.read(1)[0]
                        contents.seek(0)
                        contents.write(bytes([byte ^ 1]))
                    data = subprocess.check_output(["nix-store", "--dump", str(tree)])
                    nar.write_bytes(lzma.compress(data))
    with tarfile.open(root / "cache.tar", "w") as archive:
        for name in ("cache", "bad-signature", "bad-content", "cache.pub"):
            archive.add(root / name, arcname=name)


def check_cache(guest, port):
    # The transfer test has removed the imported closure and all its roots.
    guest.command("cd /tmp && tar xf cache.tar")
    guest.command("key=`{cat /tmp/cache.pub}")
    guest.command("fn cached { nix-store --option substituters $cache --option trusted-public-keys $key $* }")
    for name, reason in (("bad-signature", "not signed"), ("bad-content", "hash mismatch")):
        guest.command(f"cache='file:///tmp/{name}?store=/usr/local/nix/store'")
        result = guest.command("cached --realise $package; echo CACHE-STATUS:$status")
        if not re.search(r"(?m)^CACHE-STATUS:.*cc9exit=1$", result) or reason not in result:
            raise RuntimeError(f"cache did not reject {name}: {result}")
        guest.command("test ! -e $package && test ! -e $library")
        if re.search(r"(?m)^/usr/local/nix/store/", guest.command("nix-store --dump-db")):
            raise RuntimeError(f"rejected {name} registered a store path")
    guest.command("cache='file:///tmp/cache?store=/usr/local/nix/store'")
    result = guest.command("cached --realise $package --add-root /usr/local/nix/state/gcroots/cached")
    if "copying path" not in result or "building '" in result:
        raise RuntimeError(f"package was not substituted: {result}")
    guest.command("nix-store --verify-path $package $library")
    guest.command("nix-store --gc")
    guest.command("$package/bin/lua -e 'print(6 * 7)'", "42")
    check_repair(guest)
    publish_cache(guest, port)
    # Existing outputs must remain usable when their cache disappears.
    guest.command("rm -r /tmp/cache")
    guest.command("cached --realise $package")
    guest.command("rm /usr/local/nix/state/gcroots/cached; nix-store --gc")
    guest.command("test ! -e $package && test ! -e $library")
    return "signed substitution and repair, signature and content rejection, offline reuse and GC passed"


def check_repair(guest):
    guest.command("nix-store --verify --check-contents")
    for damaged in (False, True):
        if damaged:
            guest.command("chmod +w $package/bin/lua; echo damaged > $package/bin/lua")
            result = guest.command("nix-store --verify --check-contents; echo VERIFY-STATUS:$status")
            if not re.search(r"(?m)^VERIFY-STATUS:.*cc9exit=1$", result) or "was modified" not in result:
                raise RuntimeError(f"corrupt package passed verification: {result}")
        for name, reason in (("bad-signature", "not signed"), ("bad-content", "hash mismatch")):
            guest.command(f"cache='file:///tmp/{name}?store=/usr/local/nix/store'")
            result = guest.command("cached --repair-path $package; echo REPAIR-STATUS:$status")
            if not re.search(r"(?m)^REPAIR-STATUS:.*cc9exit=1$", result) or reason not in result:
                raise RuntimeError(f"repair did not reject {name}: {result}")
            if damaged:
                guest.command("cat $package/bin/lua", "damaged")
            else:
                guest.command("nix-store --verify-path $package $library")
        guest.command("cache='file:///tmp/cache?store=/usr/local/nix/store'")
        guest.command("cached --repair-path $package")
        guest.command("nix-store --verify --check-contents")
        guest.command("$package/bin/lua -e 'print(6 * 7)'", "42")
    guest.command("chmod +w $package/bin; rm $package/bin/lua")
    guest.command("cached --repair-path $package")
    guest.command("nix-store --verify --check-contents")
    guest.command("$package/bin/lua -e 'print(6 * 7)'", "42")


def interrupt_repair(guest):
    guest.command("cd /tmp && tar xf cache.tar")
    guest.command("cached --realise $package --add-root /usr/local/nix/state/gcroots/cached")
    guest.command("chmod +w $package/bin/lua; echo damaged > $package/bin/lua")
    guest.command("{exec /tmp/store-probe repair-crash $package} > /tmp/repair.log >[2=1] &")
    guest.command("for(i in 1 2 3 4 5 6 7 8 9 10) {if(! test -e /tmp/nix9-repair-ready) sleep 1}; "
                  "cat /tmp/repair.log; test -e /tmp/nix9-repair-ready")
    guest.command("test `{wc -c < $package/bin/lua} -eq 1")
    guest.command("test -e $package^.lock")
    # As in build recovery, persist the interrupted state; do not simulate torn writes.
    guest.command("echo sync >> /srv/hjfs.cmd; sleep 3")
    guest.crash()


def recover_repair(guest):
    guest.command("state=/usr/local/nix/state; store=/usr/local/nix/store")
    guest.command("test `{wc -c < $package/bin/lua} -eq 1")
    guest.command("nix-store --recover", "store recovery complete")
    guest.command("nix-store --check-validity $package $library")
    result = guest.command("nix-store --verify --check-contents; echo VERIFY-STATUS:$status")
    if not re.search(r"(?m)^VERIFY-STATUS:.*cc9exit=1$", result) or "was modified" not in result:
        raise RuntimeError(f"partial replacement passed verification: {result}")
    guest.command("key=`{cat /tmp/cache.pub}; cache='file:///tmp/cache?store=/usr/local/nix/store'")
    guest.command("nix-store --option substituters $cache --option trusted-public-keys $key --repair-path $package")
    guest.command("nix-store --verify --check-contents")
    guest.command("nix-store --gc")
    guest.command("test ! -e $store/repair-*")
    guest.command("$package/bin/lua -e 'print(6 * 7)'", "42")
    return "partial replacement, offline recovery, signed repair and GC passed"
