"""Use upstream signed file caches to substitute a native package closure."""

import lzma
import re
import shutil
import subprocess
import tarfile


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
                data = lzma.decompress(nar.read_bytes())
                if b"Lua" not in data:
                    raise RuntimeError("missing Lua corruption fixture")
                nar.write_bytes(lzma.compress(data.replace(b"Lua", b"Luz", 1)))
    with tarfile.open(root / "cache.tar", "w") as archive:
        for name in ("cache", "bad-signature", "bad-content", "cache.pub"):
            archive.add(root / name, arcname=name)


def check_cache(guest):
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
    # Existing outputs must remain usable when their cache disappears.
    guest.command("rm -r /tmp/cache")
    guest.command("cached --realise $package")
    guest.command("rm /usr/local/nix/state/gcroots/cached; nix-store --gc")
    guest.command("test ! -e $package && test ! -e $library")
    return "signed substitution, signature and content rejection, reuse and GC passed"
