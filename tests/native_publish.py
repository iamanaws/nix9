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


def writable(member):
    member.mode |= 0o200
    return member


qemu, image, nix, packages, build_packages, recipes, project, ramfs, prefix, output, lua, bzip2, clone = sys.argv[1:14]
selected = sys.argv[14:]
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
    for command in ("nix-profile", "nix9-rebuild", "nix9"):
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
    (work / "cache-build.nix").write_text(
        "let p = import <nix9>; in [\n"
        + "".join(f"  p.{name}\n" for name in selected)
        + "]\n"
    )
    for name, source in (("lua-5.4.8.tar.gz", lua), ("bzip2-1.0.8.tar.gz", bzip2)):
        (work / name).symlink_to(source)
    with tarfile.open(work / "clone-source.tar", "w", format=tarfile.USTAR_FORMAT) as tar:
        tar.add(clone, arcname="source", filter=writable)
    # These archives are build inputs, never part of the delivered runtime.
    with tarfile.open(work / "go-inputs.tar", "w", format=tarfile.USTAR_FORMAT) as tar:
        for name in ("go-bootstrap.tar.gz", "sources/go.tar.gz"):
            tar.add(Path(build_packages) / name, arcname=prefix.lstrip("/") + "/packages/" + name)
    with ArtifactServer(work, work / "published.tar") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            # All package compilation happens natively. The host only collects the cache.
            with boot(qemu, image, memory="4G" if "go" in selected else "2G") as guest:
                guest.child.timeout = 900
                guest.command(f"hget -o /tmp/bootstrap.tar http://10.0.2.2:{server.server_port}/bootstrap.tar")
                guest.command("cd / && tar xf /tmp/bootstrap.tar")
                if "go" in selected:
                    guest.command(f"cd / && hget http://10.0.2.2:{server.server_port}/go-inputs.tar | tar x")
                guest.child.timeout = 300
                guest.command(". /usr/local/pkg/nix9/activate")
                if selected:
                    guest.command(f"hget -o /tmp/cache-build.nix http://10.0.2.2:{server.server_port}/cache-build.nix")
                    for name in ("lua-5.4.8.tar.gz", "bzip2-1.0.8.tar.gz"):
                        guest.command(f"hget -o /tmp/{name} http://10.0.2.2:{server.server_port}/{name}")
                        guest.command(f"nix-store --add-fixed sha256 /tmp/{name}")
                    guest.command(f"cd /tmp && hget http://10.0.2.2:{server.server_port}/clone-source.tar | tar x")
                    imported = guest.command("nix-store --add-fixed --recursive sha256 /tmp/source")
                    source = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", imported)
                    expected = guest.command("nix-instantiate --eval --expr '(import <nix9>).clone.src.outPath'")
                    if len(source) != 1 or f'"{source[0]}"' not in expected:
                        raise RuntimeError("transferred clone source differs from its fixed-output recipe")
                    guest.command("ip/ipconfig ether /net/ether0 unbind")
                roots = "/usr/local/nix/state/gcroots"
                guest.command(f"nix-build $nix9/environment.nix --out-link {roots}/environment")
                environment = rooted(guest, roots + "/environment")
                guest.command(f"nix-build $nix9/shell.nix --out-link {roots}/shell")
                shell = rooted(guest, roots + "/shell")
                guest.child.timeout = 7200
                if selected:
                    guest.command("nix-build --no-out-link /tmp/cache-build.nix > /tmp/cache-roots")
                    outputs = guest.command("cat /tmp/cache-roots")
                else:
                    guest.command("echo -n > /tmp/cache-roots")
                    outputs = ""
                cached = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", outputs)
                if len(cached) != len(selected):
                    raise RuntimeError(f"missing selected package outputs: {outputs}")
                package_roots = [environment, shell, *cached]
                guest.command(f"package=({environment} {shell} `{{cat /tmp/cache-roots}})")
                closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command("nix-store -qR $package")))
                if any("-go-bootstrap-" in path for path in closure):
                    raise RuntimeError("native cache retains the Go seed")
                if "go" in selected:
                    compiler = cached[selected.index("go")]
                    guest.command(f"{compiler}/bin/go version", "go version go1.26.7 plan9/amd64")
                if selected:
                    guest.command("ip/ipconfig ether /net/ether0")
                publish_cache(guest, server.server_port)
            if not server.received.is_set():
                raise RuntimeError("native cache was not uploaded")
            verify_published(work, package_roots, closure)
            shutil.move(work / "published", payload / "cache")
            key = (work / "published.pub").read_text().strip()
            (payload / "cache.pub").write_text(key + "\n")
            (payload / "cache-packages").write_text(
                "".join(f"{name} {path}\n" for name, path in zip(selected, cached))
            )
            (payload / "nix.conf").write_text(
                f"substituters = file://{prefix}/cache?store=/usr/local/nix/store\n"
                f"trusted-public-keys = {key}\n"
                "!include /cfg/nix9/files/nix.conf\n"
            )
            archive(work / "bootstrap.tar")
            shutil.copyfile(work / "bootstrap.tar", output)
        finally:
            server.shutdown()
            thread.join()
print(f"Published native bootstrap: {len(closure)} cached paths")
