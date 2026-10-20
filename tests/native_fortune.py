"""Build fortune with its data, then substitute it in a fresh VM."""

import re
import tarfile
import threading

from artifacts import ArtifactServer
from guest import files_guest
from cache_publish import publish_cache, verify_published


def check_program(guest, package):
    guest.command(f"fortune={package}")
    # Neither the system's fortune data nor its optional index may be used.
    guest.command("mkdir /tmp/no-fortunes; bind /tmp/no-fortunes /sys/games/lib")
    guest.command("test -s $fortune/share/fortune/fortunes.index")
    guest.command("$fortune/bin/fortune > /tmp/fortune-result")
    guest.command("test `{wc -l < /tmp/fortune-result} -eq 1")
    guest.command("awk 'NR==FNR { entries[$0]=1; next } !($0 in entries) { exit 1 }' "
                  "$fortune/share/fortune/fortunes /tmp/fortune-result")
    guest.command("echo nix9-fortune-fixture > /tmp/single-fortune")
    guest.command("$fortune/bin/fortune /tmp/single-fortune", "nix9-fortune-fixture")
    guest.command("nix-store --verify-path $fortune")


def check_fortune(guest, qemu, image, root, archive, prefix, packages):
    guest.command(f"nix-build {packages} -A fortune --out-link /usr/local/nix/state/gcroots/fortune")
    result = guest.command("cat /usr/local/nix/state/gcroots/fortune")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-fortune$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing fortune output: {result}")
    package = paths[0]
    check_program(guest, package)
    guest.command(f"package={package}")
    closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command("nix-store -qR $package")))
    if closure != {package}:
        raise RuntimeError(f"fortune retains build dependencies: {closure}")
    root = root / "fortune"
    root.mkdir()
    with tarfile.open(archive) as tar:
        binary = tar.extractfile(prefix.lstrip("/") + "/bin/nix-store")
        (root / "nix-store").write_bytes(binary.read())
    with ArtifactServer(root, root / "published.tar") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            publish_cache(guest, server.server_port)
            if not server.received.is_set():
                raise RuntimeError("fortune cache was not published")
        finally:
            server.shutdown()
            thread.join()
    verify_published(root, package, closure)
    key = (root / "published.pub").read_text().strip()
    with files_guest(qemu, image, {"nix-store": root / "nix-store", "published.tar": root / "published.tar"}) as receiver:
        receiver.command("chmod +x /tmp/nix-store; path=(/tmp $path)")
        receiver.command("NIX_REMOTE='local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log'")
        receiver.command("test ! -e /usr/local/nix/store")
        receiver.command("cd /tmp && tar xf published.tar")
        receiver.command(f"package={package}; key='{key}'")
        receiver.command("cache='file:///tmp/published?store=/usr/local/nix/store'")
        result = receiver.command("nix-store --option substituters $cache --option trusted-public-keys $key "
                                  "--realise $package --add-root /usr/local/nix/state/gcroots/fortune")
        if "copying path" not in result or "building '" in result:
            raise RuntimeError(f"fortune was not substituted: {result}")
        receiver.command("rm -r /tmp/published; nix-store --gc")
        check_program(receiver, package)
    return "native libbio and fortune, packaged data and index, signed substitution and offline use passed"
