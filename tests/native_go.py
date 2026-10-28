"""Bootstrap Go natively, collect its seed, and compile offline after reboot."""

import contextlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import threading

from artifacts import ArtifactServer
from guest import boot


@contextlib.contextmanager
def installed_guest(qemu, disk, fixtures):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, source in fixtures.items():
            (root / name).symlink_to(Path(source).resolve())
        with ArtifactServer(root, root / "unused.tar") as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with boot(qemu, disk, snapshot=False, memory="4G") as guest:
                    guest.child.timeout = 3600
                    guest.command("ip/ipconfig -P loopback /dev/null 127.1")
                    guest.command("ip/ipconfig -P loopback /dev/null ::1")
                    base = f"http://10.0.2.2:{server.server_port}"
                    # Avoid writing a second copy of the large archive to the guest disk.
                    guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
                    guest.command("test -s /usr/local/pkg/nix9/activate")
                    for name in fixtures:
                        if name != "bootstrap.tar":
                            guest.command(f"hget -o /tmp/{name} {base}/{name}")
                    yield guest
            finally:
                server.shutdown()
                thread.join()


def writable_fixture(member):
    member.mode = 0o755 if member.isdir() else 0o644
    return member


def rooted(guest, root):
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing Go output root: {result}")
    return paths[0]


qemu, image, archive, output = sys.argv[1:]
roots = "/usr/local/nix/state/gcroots"
state = os.environ.get("NIX9_GO_TEST_STATE")
with (contextlib.nullcontext(state) if state else tempfile.TemporaryDirectory()) as directory:
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "go.qcow2"
    resume = disk.exists()
    if not resume:
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                        "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    with tarfile.open(work / "go-tests.tar", "w", format=tarfile.USTAR_FORMAT) as tar:
        tar.add(Path(__file__).with_name("go"), arcname="go", filter=writable_fixture)
        tar.add(Path(__file__).with_name("go-vendor"), arcname="go-vendor", filter=writable_fixture)
    fixtures = {"bootstrap.tar": archive, "go-tests.tar": work / "go-tests.tar",
                "go.nix": Path(__file__).with_name("go.nix")}
    with installed_guest(qemu, disk, fixtures) as guest:
        guest.command("for(directory in /tmp/go /tmp/go-vendor) { if(test -d $directory) rm -r $directory; if not status='' }")
        guest.command("cd /tmp && tar xf go-tests.tar")
        guest.command("test -s /tmp/go/main_test.go && test -s /tmp/go-vendor/modules.txt")
        guest.command(". /usr/local/pkg/nix9/activate")
        if resume:
            guest.command("nix-store --recover")
        guest.command("fn goBuild { nix-build /tmp/go.nix --argstr packages $nix9/packages $* }")
        rejected = guest.command("goBuild -A badArchive --no-out-link; echo GO-ERROR:$status")
        if not re.search(r"(?m)^GO-ERROR:.+", rejected) or "hash mismatch" not in rejected:
            raise RuntimeError(f"local Go archive hash was not checked: {rejected}")
        cached = resume and re.search(r"(?m)^GO-CACHED$", guest.command(f"if(test -r {roots}/go) echo GO-CACHED; status=''")) is not None
        if cached:
            result = guest.command("nix-instantiate --eval --expr '(import <nix9>).goBootstrap.outPath'")
            paths = re.findall(r'(?m)^"(/usr/local/nix/store/[^"\s]+)"$', result)
            if len(paths) != 1:
                raise RuntimeError(f"missing bootstrap path: {result}")
            seed = paths[0]
        else:
            guest.command(f"nix-build $nix9/packages -A goBootstrap --out-link {roots}/go-seed")
            seed = rooted(guest, roots + "/go-seed")
            guest.command(f"{seed}/bin/go version", "go version go1.26.7 plan9/amd64")
            guest.command(f"goBuild -A seedProgram --out-link {roots}/go-seed-check")
            seed_program = rooted(guest, roots + "/go-seed-check")
            guest.command(f"{seed_program}/bin/nix9-go-check", "Go plan9/amd64: HÉLLO")
            print("PASS: bootstrap Go compiles and tests in the Nix namespace", flush=True)
            result = guest.command(f"nix-build $nix9/packages -A go --out-link {roots}/go")
            if not resume and not re.search(r"building '[^']*-go-1\.26\.7\.drv'", result):
                raise RuntimeError("Go was not rebuilt natively")
        compiler = rooted(guest, roots + "/go")
        guest.command(f"{compiler}/bin/go version", "go version go1.26.7 plan9/amd64")
        closure = guest.command(f"nix-store -qR {compiler}")
        if seed in closure:
            raise RuntimeError("native Go retains its bootstrap compiler")
        guest.command(f"for(file in {roots}/go-seed {roots}/go-seed-check) {{ if(test -e $file) rm $file; if not status='' }}")
        guest.command("NIX_CONFIG='substituters ='")
        if not cached or re.search(r"(?m)^GO-SEED$", guest.command(f"if(test -e {seed}) echo GO-SEED; status=''")):
            guest.command("nix-store --gc")
        guest.command(f"test ! -e {seed}")
        print("PASS: native Go has no seed runtime dependency", flush=True)
        guest.command(f"goBuild -A program --out-link {roots}/go-program")
        program = rooted(guest, roots + "/go-program")
        guest.command(f"{program}/bin/nix9-go-check", "Go plan9/amd64: HÉLLO")
        guest.command("goBuild -A program --check --no-out-link")
        guest.command(f"goBuild -A standard --out-link {roots}/go-standard")
        guest.command(f"cat `{{cat {roots}/go-standard}}")
        rejected = guest.command("goBuild -A missingVendor --no-out-link; echo GO-ERROR:$status")
        if not re.search(r"(?m)^GO-ERROR:.+", rejected) or "inconsistent vendoring" not in rejected:
            raise RuntimeError(f"missing vendored modules were accepted: {rejected}")
        guest.command("mkdir /tmp/go/vendor; @{ cd /tmp/go-vendor; tar cf /fd/1 . } | @{ cd /tmp/go/vendor; tar xf /fd/0 }")
        guest.command("cd /tmp/go && nix-shell /tmp/go.nix --argstr packages $nix9/packages -A shell --run 'go build ''-mod=vendor'' -o /tmp/go-shell . && /tmp/go-shell'", "Go plan9/amd64: HÉLLO")
        guest.command(f"test ! -e {seed}")
        guest.command("nix-store --generate-binary-cache-key nix9-go /tmp/go.key /tmp/go.pub")
        guest.command(f"nix-store --export {program} > /tmp/go.export")
        guest.command("nix-store --store 'file:///tmp/go-cache?store=/usr/local/nix/store&secret-key=/tmp/go.key&compression=xz' --import < /tmp/go.export")
        guest.command(f"rm {roots}/go-program; nix-store --gc; test ! -e {program}")
        guest.command("cache='file:///tmp/go-cache?store=/usr/local/nix/store'; key=`{cat /tmp/go.pub}")
        guest.command(f"package={program}")
        substituted = guest.command(f"nix-store --option substituters $cache --option trusted-public-keys $key --realise $package --add-root {roots}/go-program")
        if "copying path" not in substituted or "building '" in substituted:
            raise RuntimeError(f"Go package was not substituted: {substituted}")
        if rooted(guest, roots + "/go-program") != program:
            raise RuntimeError("substituted Go package has the wrong GC root")
        guest.command(f"{program}/bin/nix9-go-check", "Go plan9/amd64: HÉLLO")
        guest.command(f"nix-store --verify-path {compiler} {program}")
        print("PASS: native packages, tests, shell, rebuild check and signed cache", flush=True)
    with boot(qemu, disk, snapshot=False, memory="4G") as guest:
        guest.child.timeout = 600
        guest.command("ip/ipconfig ether /net/ether0 unbind")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command(f"test ! -e {seed}")
        guest.command(f"{compiler}/bin/go version", "go version go1.26.7 plan9/amd64")
        guest.command("if(test -d /tmp/go-reboot-cache) rm -r /tmp/go-reboot-cache; if not status=''")
        guest.command("GOCACHE=/tmp/go-reboot-cache; GOENV=off; GOPROXY=off; GOTOOLCHAIN=local")
        guest.command(f"cd /tmp/go && {compiler}/bin/go build '-mod=vendor' -o /tmp/go-reboot .")
        guest.command("/tmp/go-reboot", "Go plan9/amd64: HÉLLO")
        guest.command(f"{program}/bin/nix9-go-check", "Go plan9/amd64: HÉLLO")
        guest.command(f"nix-store --verify-path {compiler} {program}")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "go": "1.26.7",
    "bootstrap": "seed compiler and namespace checks passed",
    "native-toolchain": "reused from developer state" if cached else "rebuilt from source",
    "seed-collection": "no bootstrap reference; seed absent after GC",
    "packages": "build, runtime, tests, deterministic rebuild and development shell passed",
    "standard-library": ["bytes", "compress/gzip", "crypto/sha256", "encoding/json", "path/filepath", "sync", "unicode/utf8"],
    "cache": "signed substitution passed",
    "offline-reboot": "compilation with an empty cache and no seed passed",
}, indent=2) + "\n")
