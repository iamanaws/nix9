"""Move a trusted native package closure to a fresh VM using upstream exports."""

import re
import socket
import tarfile
import threading

from artifacts import ArtifactServer
from guest import boot
from native_cache import cache_fixture, check_cache, verify_published
from native_cache_network import check_network_cache


def store_paths(output):
    return set(re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-[^\s]+$", output))


def export_closure(guest, package, port):
    guest.command(f"package={package}")
    paths = store_paths(guest.command("nix-store -qR $package"))
    guest.command("nix-store --export `{nix-store -qR $package} > /tmp/closure.export")
    guest.command("size=`{ls -l /tmp/closure.export | awk '{print $6}'}")
    guest.command(f"hget -r 'Content-Length: '^$size -P http://10.0.2.2:{port}/closure.export < /tmp/closure.export")
    return paths


def check_transfer(qemu, image, root, archive, prefix, sources, expected):
    # Install only the static store CLI, without the package set or sources.
    with tarfile.open(archive) as package:
        binary = package.extractfile(prefix.lstrip("/") + "/bin/nix-store")
        (root / "nix-store").write_bytes(binary.read())
    data = (root / "closure.export").read_bytes()
    (root / "truncated.export").write_bytes(data[:64])
    cache_fixture(root)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with ArtifactServer(root, root / "published.tar") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with boot(qemu, image, forward_port=port) as guest:
                guest.child.timeout = 300
                base = f"http://10.0.2.2:{server.server_port}"
                for name in ("nix-store", "closure.export", "truncated.export", "cache.tar"):
                    guest.command(f"hget -o /tmp/{name} {base}/{name}")
                guest.command("chmod +x /tmp/nix-store; path=(/tmp $path)")
                guest.command("NIX_REMOTE='local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log'")
                guest.command("test ! -e /usr/local/nix/store")
                result = guest.command("nix-store --import < /tmp/truncated.export; echo IMPORT-STATUS:$status")
                if not re.search(r"(?m)^IMPORT-STATUS:.*cc9exit=1$", result):
                    raise RuntimeError(f"truncated export was accepted: {result}")
                if store_paths(guest.command("nix-store --dump-db")):
                    raise RuntimeError("truncated NAR registered a store path")
                result = guest.command("nix-store --import < /tmp/closure.export")
                if store_paths(result) != expected:
                    raise RuntimeError(f"imported closure differs: {result}")
                guest.command(f"package={sources['package']}; library={sources['library']}")
                if store_paths(guest.command("nix-store -qR $package")) != expected:
                    raise RuntimeError("imported references changed the closure")
                guest.command("nix-store --verify-path `{nix-store -qR $package}")
                # Re-export compares the contents, references and derivers.
                guest.command("nix-store --export `{nix-store -qR $package} > /tmp/roundtrip.export")
                guest.command("cmp /tmp/closure.export /tmp/roundtrip.export")
                guest.command("nix-store --import < /tmp/closure.export")
                result = guest.command("nix-store --realise $package --add-root /usr/local/nix/state/gcroots/lua")
                if "building '" in result:
                    raise RuntimeError("imported package was rebuilt")
                guest.command("nix-store --gc")
                guest.command("nix-store --verify-path $package $library")
                guest.command("$package/bin/lua -e 'print(6 * 7)'", "42")
                guest.command("rm /usr/local/nix/state/gcroots/lua; nix-store --gc")
                if store_paths(guest.command("nix-store --dump-db")):
                    raise RuntimeError("unrooted imported closure survived GC")
                caching = check_cache(guest, server.server_port)
                if not server.received.is_set():
                    raise RuntimeError("guest did not upload its signed cache")
                network = check_network_cache(guest, qemu, image, port, base, sources)
        finally:
            server.shutdown()
            thread.join()
    verify_published(root, sources["package"], expected)
    return {"transfer": "fresh store, truncated input, round-trip, duplicate import, roots and GC passed",
            "cache": caching, "publication": "native signing, repeated publication and upstream substitution passed",
            "network": network}
