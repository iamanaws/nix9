"""Publish signed caches in a guest and verify them with upstream Nix."""

import subprocess
import tarfile


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
    packages = [package] if isinstance(package, str) else package
    store = ["nix-store", "--store", f"local?root={root}/receiver&store=/usr/local/nix/store"]
    subprocess.run(store + ["--option", "substituters", f"file://{root}/published?store=/usr/local/nix/store",
                           "--option", "trusted-public-keys", key, "--realise", *packages], check=True)
    paths = subprocess.check_output(store + ["-qR", *packages], text=True).splitlines()
    if set(paths) != expected:
        raise RuntimeError(f"native cache changed the closure: {paths}")
    subprocess.run(store + ["--verify-path", *paths], check=True)

