"""Substitute the selected native packages and use Go offline without its seed."""

import json
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import threading

from artifacts import ArtifactServer
from guest import boot


qemu, image, archive, output = sys.argv[1:]


def writable(member):
    member.mode = 0o755 if member.isdir() else 0o644
    return member


with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    with tarfile.open(archive) as tar:
        manifest = next(member for member in tar if member.name.endswith("/cache-packages"))
        expected = dict(line.split() for line in tar.extractfile(manifest).read().decode().splitlines())
    with tarfile.open(work / "project.tar", "w", format=tarfile.USTAR_FORMAT) as tar:
        tar.add(Path(__file__).with_name("go"), arcname="go", filter=writable)
        tar.add(Path(__file__).with_name("go-vendor"), arcname="go/vendor", filter=writable)
    with ArtifactServer(work, work / "unused.tar") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with boot(qemu, image, memory="4G") as guest:
                guest.child.timeout = 1800
                base = f"http://10.0.2.2:{server.server_port}"
                guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
                guest.command(f"cd /tmp && hget {base}/project.tar | tar x")
                guest.command(". /usr/local/pkg/nix9/activate")
                guest.command("ip/ipconfig ether /net/ether0 unbind")
                guest.command("test ! -e $nix9/packages/go-bootstrap.tar.gz && test ! -e $nix9/packages/sources/go.tar.gz")
                result = guest.command(
                    "nix-build --max-jobs 0 --no-out-link --expr "
                    "'let p = import <nix9>; in map (name: p.${name}) "
                    "(import (builtins.getEnv \"nix9\" + \"/packages/cache-packages.nix\"))' > /tmp/cache-roots"
                )
                paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat /tmp/cache-roots"))
                if paths != list(expected.values()) or "building '" in result or "copying path" not in result:
                    raise RuntimeError(f"selected packages were not substituted: {result}")
                compiler = expected["go"]
                guest.command(f"{compiler}/bin/go version", "go version go1.26.7 plan9/amd64")
                closure = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command(f"nix-store -qR {compiler}"))
                if closure != [compiler]:
                    raise RuntimeError(f"Go retains build prerequisites: {closure}")
                guest.command("mkdir -p /tmp/go-cache /tmp/go-tmp /tmp/go-path")
                guest.command("GOCACHE=/tmp/go-cache; GOTMPDIR=/tmp/go-tmp; GOPATH=/tmp/go-path; GOENV=off; GOPROXY=off; GOSUMDB=off; GOTOOLCHAIN=local; GOMAXPROCS=2")
                guest.command(f"cd /tmp/go && {compiler}/bin/go test '-mod=vendor' -p 2 .")
                guest.command(f"{compiler}/bin/go build '-mod=vendor' -p 2 -o /tmp/go-check .")
                guest.command("/tmp/go-check", "Go plan9/amd64: HÉLLO")
                guest.command(f"{compiler}/bin/gofmt -w main.go main_test.go")
                guest.command("nix-store --verify-path `{cat /tmp/cache-roots}")
                # Selecting a complete release relocates the recipes and file cache.
                guest.command("nix-build /usr/local/pkg/nix9/release.nix --out-link /usr/local/nix/state/gcroots/cache-release")
                guest.command("release=`{cat /usr/local/nix/state/gcroots/cache-release}")
                guest.command("nix-profile /usr/local/nix/state/gcroots/nix9 set $release")
                guest.command(". /usr/local/pkg/nix9/activate")
                relocated = guest.command("nix-build $nix9/packages -A go --max-jobs 0 --no-out-link")
                if compiler not in relocated or "building '" in relocated:
                    raise RuntimeError(f"selected release changed Go's cache identity: {relocated}")
        finally:
            server.shutdown()
            thread.join()
Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "native-packages": len(expected),
    "substitution": "all selected packages, offline, with builds disabled",
    "go": "compile, test and gofmt with an empty build cache and no seed/source archives",
    "release": "Go cache identity survives complete release selection",
}, indent=2) + "\n")
