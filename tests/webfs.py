"""Build webfs natively and check both builds with Nix fetches and signed caches."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading

from artifacts import ArtifactServer
from eval_fetch import check_eval_fetch
from guest import boot
from native_cache import cache_fixture
from native_cache_http import check_http_cache


def store_path(guest, command):
    output = guest.command(command)
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-[^\s]+$", output)
    if len(paths) != 1:
        raise RuntimeError(f"missing store output: {output}")
    return paths[0]


def install_nix(guest, base, prefix):
    guest.command(f"cd / && hget {base}/nix.tar | tar x")
    guest.command(f". {prefix}/activate")


qemu, image, archive, prefix, packages_archive, packages, cross, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for name, source in (("nix.tar", archive), ("packages.tar", packages_archive),
                         ("cross-webfs", Path(cross) / "bin/webfs"),
                         ("webfs.nix", Path(__file__).with_suffix(".nix"))):
        shutil.copyfile(source, root / name)
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(root / "key.pem"), "-out", str(root / "cert.pem"),
        "-days", "1", "-subj", "/CN=wrong.example",
        "-addext", "subjectAltName=DNS:wrong.example",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for variant in ("cross", "native"):
        fixtures = root / variant
        fixtures.mkdir()
        for name in ("cert.pem", "key.pem"):
            shutil.copyfile(root / name, fixtures / name)
    with ArtifactServer(root, root / "outputs.tar") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://10.0.2.2:{server.server_port}"
            with boot(qemu, image) as guest:
                guest.child.timeout = 900
                install_nix(guest, base, prefix)
                guest.command(f"hget -o /tmp/cross-webfs {base}/cross-webfs")
                guest.command("chmod +x /tmp/cross-webfs; bind /tmp/cross-webfs /bin/webfs")
                cross_result = check_eval_fetch(guest, root / "cross")
                guest.command("rm -rf /tmp/nix9-archive-temp /tmp/nix9-eval-fetch-cache /tmp/nix9-eval-fetch-empty-cache")
                guest.command(f"cd / && hget {base}/packages.tar | tar x")
                guest.command(f"hget -o /tmp/webfs.nix {base}/webfs.nix")
                native = store_path(guest, f"nix-build {packages} -A webfs --no-out-link")
                guest.command(f"cp {native}/bin/webfs /tmp/native-webfs; chmod +x /tmp/native-webfs")
                package = store_path(guest, f"nix-build /tmp/webfs.nix --argstr packages {packages} --no-out-link")
                library = store_path(guest, f"nix-store -q --references {package}")
                guest.command(f"nix-store --export `{{nix-store -qR {package}}} > /tmp/closure.export")
                guest.command("cd /tmp && tar cf outputs.tar native-webfs closure.export")
                guest.command("size=`{ls -l /tmp/outputs.tar | awk '{print $6}'}")
                guest.command(f"hget -r 'Content-Length: '^$size -P {base}/outputs.tar < /tmp/outputs.tar")
                if not server.received.is_set():
                    raise RuntimeError("guest did not upload its webfs build and cache fixture")
                guest.command("bind /tmp/native-webfs /bin/webfs")
                native_result = check_eval_fetch(guest, root / "native")
            with tarfile.open(root / "outputs.tar") as archive_file:
                archive_file.extractall(root, filter="data")
            cache_fixture(root)
            with boot(qemu, image) as guest:
                guest.child.timeout = 300
                install_nix(guest, base, prefix)
                guest.command(f"hget -o /tmp/native-webfs {base}/native-webfs")
                guest.command("chmod +x /tmp/native-webfs; bind /tmp/native-webfs /bin/webfs")
                guest.command(f"package={package}; library={library}")
                http = check_http_cache(guest, root, program="answer", arguments="")
        finally:
            server.shutdown()
            thread.join()
Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "cross": cross_result, "native": native_result, "cache": http,
}, indent=2) + "\n")
