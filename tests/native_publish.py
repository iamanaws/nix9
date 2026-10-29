"""Build a signed native development cache and package it for installation."""

from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
import threading

from artifacts import ArtifactServer
from cache_publish import publish_cache, verify_published
from guest import boot


def rooted(guest, root):
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing output root: {result}")
    return paths[0]


qemu, image, nix, packages, recipes, project, ramfs, prefix, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    payload = work / "root" / prefix.lstrip("/")
    shutil.copytree(nix, payload)
    payload.chmod(0o755)
    shutil.copytree(packages, payload / "packages")
    for name in ("environment.nix", "shell.nix", "release.nix", "activate.rc"):
        shutil.copyfile(Path(recipes) / name, payload / name)
    shutil.copytree(project, payload / "hello")
    shutil.copytree(ramfs, payload / "ramfs")
    for path in payload.rglob("*"):
        path.chmod(path.stat().st_mode | 0o200)
    # Keep the example tied to this archive's package set.
    for name in ("default.nix", "shell.nix"):
        path = payload / "hello" / name
        path.write_text(path.read_text().replace("/usr/local/pkg/native-packages", "<nix9>"))
    for command in ("nix-profile", "nix9-rebuild"):
        shutil.copy(payload / "packages" / "bin" / command, payload / "bin" / command)
    activate = f"nix9Next={prefix}\n" + (payload / "activate.rc").read_text()
    (payload / "activate").write_text(activate)
    selector = work / "root/usr/local/pkg/nix9"
    selector.mkdir()
    shutil.copyfile(payload / "packages" / "profile", selector / "profile")
    shutil.copyfile(payload / "packages/system/machine.rc", selector / "machine")
    (selector / "activate").write_text(
        ". /usr/local/pkg/nix9/machine && {\n"
        "if(test -r /usr/local/nix/state/gcroots/nix9) {\n"
        "\t. /usr/local/pkg/nix9/profile /usr/local/nix/state/gcroots/nix9\n"
        "}\n"
        f"if not . {prefix}/activate\n"
        "}\n"
    )
    (selector / "release.nix").write_text(f"import {prefix}/release.nix\n")

    def archive(destination):
        with tarfile.open(destination, "w", format=tarfile.USTAR_FORMAT) as tar:
            tar.add(work / "root/usr", arcname="usr")

    archive(work / "bootstrap.tar")
    with ArtifactServer(work, work / "published.tar") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            # All package compilation happens natively. The host only collects the cache.
            with boot(qemu, image) as guest:
                guest.child.timeout = 900
                guest.command(f"hget -o /tmp/bootstrap.tar http://10.0.2.2:{server.server_port}/bootstrap.tar")
                guest.command("cd / && tar xf /tmp/bootstrap.tar")
                guest.child.timeout = 300
                guest.command(". /usr/local/pkg/nix9/activate")
                roots = "/usr/local/nix/state/gcroots"
                guest.command(f"nix-build $nix9/environment.nix --out-link {roots}/environment")
                environment = rooted(guest, roots + "/environment")
                guest.command(f"nix-build $nix9/shell.nix --out-link {roots}/shell")
                shell = rooted(guest, roots + "/shell")
                guest.command(f"package=({environment} {shell})")
                closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command("nix-store -qR $package")))
                publish_cache(guest, server.server_port)
            if not server.received.is_set():
                raise RuntimeError("native cache was not uploaded")
            verify_published(work, [environment, shell], closure)
            shutil.move(work / "published", payload / "cache")
            key = (work / "published.pub").read_text().strip()
            (payload / "cache.pub").write_text(key + "\n")
            (payload / "nix.conf").write_text(
                f"substituters = file://{prefix}/cache?store=/usr/local/nix/store\n"
                f"trusted-public-keys = {key}\n"
            )
            archive(work / "bootstrap.tar")
            shutil.copyfile(work / "bootstrap.tar", output)
        finally:
            server.shutdown()
            thread.join()
print(f"Published native bootstrap: {len(closure)} cached paths")
