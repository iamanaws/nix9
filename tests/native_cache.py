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


def publish_cache(guest, port):
    guest.command("nix-store --generate-binary-cache-key nix9-native /tmp/published.key /tmp/published.pub")
    guest.command("nix-store --export `{nix-store -qR $package} > /tmp/published.export")
    guest.command("destination='file:///tmp/published?store=/usr/local/nix/store&secret-key=/tmp/published.key&compression=xz'")
    # Publishing an existing closure again must also succeed.
    for _ in range(2):
        guest.command("nix-store --store $destination --import < /tmp/published.export")
    guest.command("cd /tmp && tar cf published.tar published published.pub")
    guest.command("size=`{ls -l /tmp/published.tar | awk '{print $6}'}")
    guest.command(f"hget -r 'Content-Length: '^$size -P http://10.0.2.2:{port}/published.tar < /tmp/published.tar")


def verify_published(root, package, expected):
    # Upstream Nix must accept the guest's signatures and complete closure.
    with tarfile.open(root / "published.tar") as archive:
        archive.extractall(root, filter="data")
    key = (root / "published.pub").read_text().strip()
    store = ["nix-store", "--store", f"local?root={root}/receiver&store=/usr/local/nix/store"]
    subprocess.run(store + ["--option", "substituters", f"file://{root}/published?store=/usr/local/nix/store",
                           "--option", "trusted-public-keys", key, "--realise", package], check=True)
    paths = subprocess.check_output(store + ["-qR", package], text=True).splitlines()
    if set(paths) != expected:
        raise RuntimeError(f"native cache changed the closure: {paths}")
    subprocess.run(store + ["--verify-path", *paths], check=True)


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
