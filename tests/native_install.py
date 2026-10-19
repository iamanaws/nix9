"""Install native Nix, reuse packages and recover an interrupted build."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from guest import boot
from artifacts import ArtifactServer
from native_fetch import fetch_fixtures, check_fetch
from native_sources import source_server, check_sources
from native_fortune import check_fortune
from native_project import check_project
from native_phases import check_phases
from native_recovery import interrupt_build, recover_build
from native_transfer import export_closure, check_transfer


qemu, image, archive, prefix, packages_archive, packages, output, lua_archive, probe, elf2aout, project_source = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    disk = root / "persistent.qcow2"
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    shutil.copyfile(archive, root / "package.tar")
    shutil.copyfile(packages_archive, root / "packages.tar")
    shutil.copyfile(Path(__file__).with_name("recovery.nix"), root / "recovery.nix")
    subprocess.run([sys.executable, elf2aout, probe, str(root / "store-probe")], check=True)
    (root / "project").mkdir()
    for name in ("default.nix", "hello.c"):
        shutil.copyfile(Path(project_source) / name, root / "project" / name)
    shutil.copyfile(Path(__file__).with_name("phases.nix"), root / "phases.nix")
    fetch_fixtures(root)
    with source_server(root, lua_archive) as tls_port, \
            ArtifactServer(root, root / "closure.export") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with boot(qemu, disk, snapshot=False) as guest:
                guest.child.timeout = 300
                guest.command(f"hget -o /tmp/package.tar http://10.0.2.2:{server.server_port}/package.tar")
                guest.command("cd / && tar xf /tmp/package.tar")
                guest.command(f"hget -o /tmp/recovery.nix http://10.0.2.2:{server.server_port}/recovery.nix")
                guest.command(f"hget -o /tmp/store-probe http://10.0.2.2:{server.server_port}/store-probe")
                guest.command("chmod +x /tmp/store-probe")
                guest.command(f". {prefix}/activate")
                guest.command("nix-instantiate --eval --expr '6 * 7'", "42")
                guest.command(f"test ! -e {prefix}/share/nix9")
                guest.command(f"hget -o /tmp/packages.tar http://10.0.2.2:{server.server_port}/packages.tar")
                guest.command("cd / && tar xf /tmp/packages.tar && rm /tmp/packages.tar")
                phases = check_phases(guest, packages, server.server_port)
                project = check_project(guest, server.server_port)
                fortune = check_fortune(guest, qemu, image, root, archive, prefix, packages)
                fetching = check_fetch(guest, packages, server.server_port)
                sources = check_sources(guest, packages, server.server_port, tls_port)
                closure = export_closure(guest, sources["package"], server.server_port)
                if not server.received.is_set():
                    raise RuntimeError("guest did not upload the closure")
                drv_root = "/usr/local/nix/state/gcroots/sha1sum-drv"
                guest.command(
                    f"nix-instantiate --add-root {drv_root} "
                    f"--expr '(import {packages}).sha1sum'", drv_root)
                result = guest.command(f"cat {drv_root}")
                paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-sha1sum\.drv$", result)
                if len(paths) != 1:
                    raise RuntimeError(f"missing installed derivation: {result}")
                drv = paths[0]
                guest.command("nix-store --gc")
                guest.command(f"nix-store --check-validity {drv}")
                permanent = "/usr/local/nix/state/gcroots/sha1sum"
                guest.command(f"nix-build {packages} -A sha1sum --out-link {permanent}")
                result = guest.command(f"cat {permanent}")
                paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-sha1sum$", result)
                if len(paths) != 1:
                    raise RuntimeError(f"missing installed output: {result}")
                package = paths[0]
                guest.command(f"rm {drv_root}")
                guest.command(f"echo -n abc | {package}/bin/sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
                guest.command(f"nix-store --verify-path {drv} {package}")
                guest.command("rm /tmp/package.tar")
        finally:
            server.shutdown()
            thread.join()
    # A second QEMU process uses the same overlay, without any host file server.
    with boot(qemu, disk, snapshot=False) as guest:
        guest.command(f". {prefix}/activate")
        guest.command(f"cat {permanent}", package)
        guest.command(f"{sources['package']}/bin/lua -e 'print(6 * 7)'", "42")
        guest.command(f"nix-store --verify-path {sources['package']} {sources['library']}")
        guest.command("echo disposable > /tmp/gc-unused")
        result = guest.command("nix-store --add /tmp/gc-unused")
        unused = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-gc-unused$", result)
        if len(unused) != 1:
            raise RuntimeError(f"missing unrooted store path: {result}")
        guest.command("nix-store --gc")
        guest.command(f"test ! -e {unused[0]}")
        guest.command(f"nix-store --check-validity {drv} {package}")
        result = guest.command(f"nix-store --realise {drv}", package)
        if re.search(r"(?m)^building '", result):
            raise RuntimeError(f"persisted package was rebuilt: {result}")
        guest.command(f"nix-store --verify-path {drv} {package}")
        guest.command(f"echo -n abc | {package}/bin/sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
        guest.command(f"rm {permanent}")
        guest.command("nix-store --gc")
        guest.command(f"test ! -e {package} && test ! -e {drv}")
        interrupt_build(guest)
    with boot(qemu, disk, snapshot=False) as guest:
        guest.command(f". {prefix}/activate")
        recovery = recover_build(guest)
        guest.command(f"nix-store --verify-path {sources['package']} {sources['library']}")
        guest.command(f"{sources['package']}/bin/lua -e 'print(6 * 7)'", "42")
        guest.command("rm /usr/local/nix/state/gcroots/lua; nix-store --gc")
        guest.command(f"test ! -e {sources['package']} && test ! -e {sources['library']}")
    transfer = check_transfer(qemu, image, root, archive, prefix, sources, closure)

Path(output, "native-install.json").write_text(json.dumps({
    "prefix": prefix,
    "derivation": drv,
    "output": package,
    "installation": "passed",
    "fortune": fortune,
    "standalone-project": project,
    "phases": phases,
    "fetching": fetching,
    "sources": sources,
    "native-build": "passed",
    "gc-before-build": "passed",
    "reuse-after-reboot": "passed",
    "permanent-roots-and-gc": "passed",
    "interrupted-build-recovery": recovery,
    "closure-transfer": transfer,
}, indent=2) + "\n")
print("PASS: installed native Nix builds, reuses packages and recovers an interrupted build")
