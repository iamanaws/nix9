"""Publish, upgrade and roll back shared CPU roots while retaining machine state."""

from contextlib import ExitStack, contextmanager, nullcontext
import functools
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

from boot_medium import boot_medium
from guest import boot

ROOTS = "/usr/local/nix/state/gcroots"
PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"
CPUS = ("build", "batch")


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def paths(output):
    return re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", output)


def rejected(guest, command, reason):
    output = guest.command("rc -c " + quote(command) + "; echo ROOT-ERROR:$status")
    if not re.search(r"(?m)^ROOT-ERROR:.+", output) or reason not in output or "syntax error" in output:
        raise RuntimeError(f"unexpected failure: {command}: {output}")


def until(guest, command):
    for _ in range(40):
        output = guest.command(command + "; echo ROOT-WAIT:$status")
        if re.search(r"(?m)^ROOT-WAIT:$", output):
            return
        time.sleep(0.2)
    raise RuntimeError(f"timed out: {command}: {output}")


def nvram(key):
    fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
              b"nix9.netroot".ljust(48, b"\0"), key)
    return b"".join(field + bytes([(9 + sum(field)) % 256]) for field in fields)


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_NETROOT_TEST_STATE")
with ExitStack() as stack:
    work = Path(stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory()))
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    for file in ("netroot.nix", "netroot-project.nix", "machine-newns.c"):
        shutil.copyfile(Path(__file__).with_name(file), work / file)
    (work / "cwfs.setup").write_text("service files\nconfig /adm/storage/config\n"
        "filsys main cw0fw1\nfilsys dump o\nream main\nend\n")
    keys = {name: secrets.token_bytes(16) for name in ("files", "glenda", *CPUS)}
    for name, key in keys.items():
        roles = ("client",) if name == "glenda" else ("server", "speakfor") if name in CPUS else ("server",)
        for suffix, data in (("keys", "".join(f"key proto=dp9ik dom=nix9.netroot user={name} role={role} "
                f"!hex={key.hex()} !password=______\n" for role in roles).encode()), ("aes", key)):
            file = work / (name + "." + suffix)
            file.write_bytes(data)
            file.chmod(0o600)
    (work / "server.nvram").write_bytes(nvram(keys["glenda"]))
    (work / "server.nvram").chmod(0o600)
    http = stack.enter_context(http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join)
    stack.callback(http.shutdown)
    base = f"http://10.0.2.2:{http.server_port}"

    def download(guest, name, destination=None, private=False):
        destination = destination or "/tmp/" + name
        if private:
            guest.command(f"echo -n > {destination}; chmod 600 {destination}")
        guest.command(f"hget -o {destination} {base}/{name}")

    peers, reservations = [], {}
    for address, port in (("10.0.2.100", 567), ("10.0.2.101", 564),
                          ("10.0.2.102", 17019), ("10.0.2.103", 17019), ("10.0.2.100", 5356),
                          ("10.0.2.102", 17024)):
        reservation = stack.enter_context(socket.socket())
        reservation.bind(("127.0.0.1", 0))
        host = reservation.getsockname()[1]
        peers.append((address, port, host))
        reservations[host] = reservation
    # The secstore reservation deliberately refuses the optional connection.
    # Otherwise a user-network alias with no forwarded port stalls during ARP.
    peers.append(("10.0.2.104", http.server_port, http.server_port))

    def disk(path, backing):
        if path.exists():
            raise RuntimeError(f"refusing to replace {path}")
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2", "-F", "qcow2",
                        "-b", str(Path(backing).resolve()), str(path)], check=True)

    foundation = work / "bootstrap.qcow2"
    disk(foundation, image)
    with boot(qemu, foundation, snapshot=False) as guest:
        guest.child.timeout = 1200
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix-build '<nix9>' -A cwfs -A auth -A rcpu -A ndb --out-link " + ROOTS + "/netroot-tools")

    disks, systems, bundles, boot_artifacts = {}, {}, {}, {}
    root_bundles, root_directories = {}, {}
    selected_roots = dict.fromkeys(CPUS, "stable")
    storage_drives = []
    for name, size in (("cache", 3), ("worm", 8)):
        volume = work / (name + ".raw")
        with volume.open("xb") as file:
            file.truncate(size * 1024 ** 3)
        storage_drives.extend(("-drive", f"file={volume},format=raw,if=virtio"))
    project_drv = project_output = None
    for name in ("auth", "files"):
        disks[name] = work / (name + ".qcow2")
        disk(disks[name], foundation)
        with boot(qemu, disks[name], snapshot=False, qemu_options=storage_drives if name == "files" else ()) as guest:
            guest.child.timeout = 1200
            guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init " + name)
            download(guest, "server.nvram", "/tmp/server.nvram", private=True)
            guest.command("dd -if /tmp/server.nvram -of /dev/sdF0/nvram -bs 126 -count 1")
            download(guest, "netroot.nix")
            if name == "auth":
                guest.command("rm -f /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                for identity in keys:
                    download(guest, identity + ".aes", private=True)
                    guest.command(f"mkdir /mnt/keys/{identity}; cp /tmp/{identity}.aes /mnt/keys/{identity}/aeskey")
            else:
                download(guest, "files.keys", "/adm/files.keys", private=True)
                guest.command("mkdir /adm/storage; chmod 700 /adm/storage")
                for volume, blocks in (("config", 1),):
                    guest.command(f"dd -if /dev/zero -of /adm/storage/{volume} -bs 16384 -count 1 -oseek {blocks-1}")
                    guest.command("chmod 600 /adm/storage/" + volume)
                download(guest, "cwfs.setup")
                guest.command("echo 'w0 /dev/sdG0/data' > /tmp/devices; echo 'w1 /dev/sdH0/data' >> /tmp/devices")
                guest.command(f"cwfs=`{{cat {ROOTS}/netroot-tools}}; fsmempercent=5 $cwfs/bin/cwfs64x "
                              "-c -f /adm/storage/config -m /tmp/devices -n provision -a tcp!*!564 < /tmp/cwfs.setup")
                for command in ("users default", "create /adm adm adm 775 d", "create /adm/users adm adm 664",
                                "create /usr adm adm 775 d", "newuser glenda", "create /systems glenda glenda 775 d",
                                "create /machines glenda glenda 775 d"):
                    guest.command("echo " + quote(command) + " >> /srv/provision.cmd")
                guest.command("echo halt >> /srv/provision.cmd; while(test -e /srv/provision.cmd) sleep 1; status=''")
                for version in ("first", "second"):
                    guest.command(f"nix-build /tmp/netroot.nix -A {version}.build --out-link {ROOTS}/netroot-{version}")
                    bundles[version] = paths(guest.command(f"cat {ROOTS}/netroot-{version}"))[0]
                for cpu in CPUS:
                    systems[cpu] = {version: paths(guest.command(f"cat {bundle}/systems/{cpu}"))[0]
                                    for version, bundle in bundles.items()}
                    boot_artifacts[cpu] = {version: paths(guest.command(f"cat {bundle}/boot/{cpu}/path"))[0]
                                           for version, bundle in bundles.items()}
                for root, version in (("stable", "first"), ("next", "second")):
                    root_bundles[root] = paths(guest.command(f"cat {bundles[version]}/roots/{root}"))[0]
                    root_directories[root] = "/systems/" + root_bundles[root].rsplit("/", 1)[1]
                guest.command("nix-build /tmp/netroot.nix -A first.roots.stable --check --no-out-link")
                targets = [path for machine in (systems, boot_artifacts) for versions in machine.values() for path in versions.values()]
                guest.command("echo -n > /tmp/targets")
                for target in sorted(set(targets)):
                    guest.command(f"echo {target} >> /tmp/targets")
                guest.command("nix-store -qR `{cat /tmp/targets} > /tmp/closure-paths")
                guest.command("nix-store --export `{cat /tmp/closure-paths} > /tmp/systems.export")
                download(guest, "netroot-project.nix")
                project_drv = paths(guest.command("nix-instantiate /tmp/netroot-project.nix"))[0]
                project_output = paths(guest.command("nix-store -q --outputs " + project_drv))[0]
                guest.command("nix-store --export `{nix-store -qR --include-outputs " + project_drv + "} > /tmp/project.export")
            guest.command(f"mkdir -p /cfg/{name}/service")
            guest.command(f"echo '(import ./netroot.nix {{}}).first.systems.{name}' > /tmp/system.nix")
            guest.command("nix9-rebuild switch /tmp/system.nix")
            guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    @contextmanager
    def server(name):
        address, port, host = peers[0 if name == "auth" else 1]
        reservations[host].close()
        with boot(qemu, disks[name], snapshot=False, cpu=True, configure_network=False, prompt=PROMPT,
                  forward_ports=[(host, port)], guest_forwards=peers, network_options=("restrict=on",),
                  qemu_options=storage_drives if name == "files" else ()) as guest:
            guest.child.timeout = 1200
            guest.command(". /usr/local/pkg/nix9/system")
            until(guest, f"netstat -n | grep 'Listen *{port} '")
            yield guest

    auth = stack.enter_context(server("auth"))
    files = stack.enter_context(server("files"))
    base = f"http://10.0.2.104:{http.server_port}"
    # HTTP is needed only to provision the fixture; all root mounts use authenticated 9P.
    files.command("webfs")
    download(files, "glenda.keys", "/tmp/client.keys", private=True)
    files.command("cat /tmp/client.keys > /mnt/factotum/ctl; mount -c /srv/cwfs-nix9 /n/site main")
    files.command(f"rc {root_bundles['stable']}/publish /n/site")
    for root_part in ("bin", "cfg", "dev", "env", "fd", "mnt", "net", "n", "proc", "root", "srv", "tmp",
                      "usr/local/nix/store", "usr/local/nix/state", "usr/local/pkg"):
        files.command(f"test -d /n/site{root_directories['stable']}/{root_part}")
    rejected(files, f"rc {root_bundles['stable']}/publish /n/site", "root version already exists")
    files.command(f"mkdir /n/site{root_directories['next']}.partial")
    rejected(files, f"rc {root_bundles['next']}/publish /n/site", "partial publication already exists")
    files.command(f"rm /n/site{root_directories['next']}.partial; test ! -e /n/site{root_directories['next']}")
    download(files, "machine-newns.c")
    files.command("cd /tmp && 6c machine-newns.c && 6l -o /tmp/check-newns machine-newns.6")
    download(files, "bootstrap.tar", "/tmp/node-bootstrap.tar")
    sizes = {}
    for cpu in CPUS:
        artifact = boot_artifacts[cpu]["first"]
        files.command(f"rc {artifact}/prepare /n/site /tmp/node-bootstrap.tar")
        rejected(files, f"rc {artifact}/prepare /n/site /tmp/node-bootstrap.tar", "machine state already exists")
        directory = "/n/site/machines/" + cpu
        files.command(f"echo {cpu} > {directory}/usr/glenda/home-marker")
        files.command(f"echo '# writable home' >> {directory}/usr/glenda/lib/profile")
        files.command(f"cp /tmp/check-newns {directory}/tmp/check-newns")
        download(files, cpu + ".keys", directory + "/adm/cpu.keys", private=True)
        for fixture in ("systems.export", "project.export"):
            files.command(f"cp /tmp/{fixture} {directory}/tmp/{fixture}")
        settings = files.command("cat " + artifact + "/plan9.ini")
        configuration = "\n".join(line for line in settings.splitlines() if re.match(r"^[a-z0-9]+=", line)) + "\n"
        disks[cpu] = work / (cpu + ".qcow2")
        sizes[cpu] = boot_medium(qemu, image, disks[cpu], configuration, nvram(keys["glenda"]))
        if cpu == "build":
            bad_medium = work / "bad-key.qcow2"
            boot_medium(qemu, image, bad_medium, configuration, nvram(secrets.token_bytes(16)))
    files.command("echo dump >> /srv/cwfs-nix9.cmd")
    print("PASS: native inventory artifacts prepare distinct state and kernel-only boot media", flush=True)

    @contextmanager
    def cpu(name, *, medium=None, failure=None):
        address = peers[2 if name == "build" else 3][0]
        forwarded = [(port, host) for peer, port, host in peers if peer == address]
        for _, host in forwarded:
            reservations[host].close()
        options = ("restrict=on",) + tuple(f"hostfwd=tcp:127.0.0.1:{host}-{address}:{port}"
                                         for port, host in forwarded)
        with boot(qemu, medium or disks[name], snapshot=False, cpu=True, configure_network=False,
                  prompt=failure or PROMPT, boot_prompt=False, guest_forwards=peers,
                  network_options=options) as guest:
            guest.child.timeout = 1200
            if failure:
                guest.crash()
            else:
                root = selected_roots[name]
                guest.command("cat /network-root-marker", "root-one" if root == "stable" else "root-two")
                guest.command("cat /cfg/nix9/root", root_directories[root].rsplit("/", 1)[1])
                guest.command("cat /usr/glenda/home-marker", name)
                guest.command("test ! -w /network-root-marker")
                guest.command("echo -n >> /sys/lib/tls/webfs/revoked")
                guest.command("echo `{ls -p /dev/sdF0}")
                guest.command("test ! -e /dev/sdF0/fs && test ! -e /dev/sdF0/fscache")
                guest.command(". /usr/local/pkg/nix9/activate; echo $nix9MachineId", name)
                guest.command("cat /usr/local/nix/state/machine-id", name)
            yield guest

    def untrusted_service(version):
        until(build, "netstat -n | grep 'Listen *17024 '")
        with socket.create_connection(("127.0.0.1", peers[5][2]), timeout=60) as connection:
            response = bytearray()
            while data := connection.recv(4096):
                response.extend(data)
        if response.decode().splitlines() != ["none", "keys-protected", version]:
            raise RuntimeError(f"untrusted service lost its system namespace: {response!r}")

    for name in CPUS:
        with cpu(name) as guest:
            guest.command("nix-store --import < /tmp/systems.export")
            guest.command("nix-store --import < /tmp/project.export")
            for version, artifact in boot_artifacts[name].items():
                guest.command(f"nix-store --realise {artifact} --add-root {ROOTS}/boot-{version}")
            for root in root_bundles.values():
                rejected(guest, "nix-store --check-validity " + root, "not valid")
            guest.command("nix9-rebuild select " + systems[name]["first"])
            guest.command(". /usr/local/pkg/nix9/system")
            guest.command("nix-store --realise " + project_drv + " --add-root " + ROOTS + "/project", ROOTS + "/project")
            guest.command("cat " + ROOTS + "/project", project_output)
            guest.command(project_output + "/bin/hello", "hello from a network-root CPU")
            guest.command("cat " + project_output + "/compiled-on; echo", name)
            guest.command("nix-store --verify-path " + project_output)
            guest.command("/tmp/check-newns '. /usr/local/pkg/nix9/system; echo $nix9MachineId'", name)
        files.command("test -e /srv/cwfs-nix9; cat /usr/local/nix/state/machine-id", "files")
    rejected(files, "nix-store --check-validity " + project_output, "not valid")
    print("PASS: CPUs boot without a local OS, build natively, and retain separate stores through newns", flush=True)

    with cpu("batch") as batch:
        with cpu("build") as build:
            for name, guest in (("build", build), ("batch", batch)):
                guest.command(". /usr/local/pkg/nix9/system")
                guest.command("cat $nix9SystemRoot^-boot", systems[name]["first"])
                until(guest, "netstat -n | grep 'Listen *17019 '")
                files.command("rcpu -u glenda -h " + name + " -k 'dom=nix9.netroot' -c "
                              + quote("echo `{cat /dev/sysname}; nix-store --verify-path " + project_output), name)
            untrusted_service("one")
            files.command(f"rc {root_bundles['next']}/publish /n/site")
            build.command("cat /network-root-marker", "root-one")
            batch.command("cat /network-root-marker", "root-one")
            first_boot = boot_artifacts["build"]["first"]
            next_boot = boot_artifacts["build"]["second"]
            rejected(files, f"rc {next_boot}/select /n/site /tmp", "machine identity mismatch")
            build.command("9fs 9fat; cp /n/9fat/plan9.ini /tmp/original.ini")
            build.command("mkdir /tmp/wrong-medium; echo 'nix9machine=batch' > /tmp/wrong-medium/plan9.ini")
            rejected(build, f"rc {next_boot}/select /root /tmp/wrong-medium", "boot medium belongs to another machine")
            build.command("cmp /n/9fat/plan9.ini /tmp/original.ini")
            build.command(f"rc {next_boot}/select /root /n/9fat")
            build.command("cmp /n/9fat/plan9.bak /tmp/original.ini")
            build.command("cat /network-root-marker", "root-one")
            build.command("cat $nix9SystemRoot^-boot", systems["build"]["first"])
            build.command("nix9-rebuild select " + systems["build"]["second"])
            build.command(". /usr/local/pkg/nix9/system; cat /cfg/nix9/files/version", "two")
            build.command("/tmp/check-newns '. /usr/local/pkg/nix9/system; cat /cfg/nix9/files/version'", "two")
            batch.command("cat /cfg/nix9/files/version", "batch")
            build.command("nix-store --gc; nix-store --verify-path " + systems["build"]["first"])
    selected_roots["build"] = "next"
    with cpu("batch") as batch, cpu("build") as build:
        batch.command("cat /network-root-marker", "root-one")
        build.command("cat /network-root-marker", "root-two")
        build.command(". /usr/local/pkg/nix9/system; cat /cfg/nix9/files/version", "two")
        build.command("echo `{cat /dev/sysname}", "worker")
        untrusted_service("two")
        build.command("/tmp/check-newns '. /usr/local/pkg/nix9/system; echo $nix9MachineId'", "build")
        build.command("/tmp/check-newns 'cat /network-root-marker'", "root-two")
        build.command("nix-store --verify-path " + project_output)
        build.command(project_output + "/bin/hello", "hello from a network-root CPU")
        build.command("nix9-rebuild rollback; . /usr/local/pkg/nix9/system; cat /cfg/nix9/files/version", "one")
        build.command("cat /network-root-marker", "root-two")
        build.command("9fs 9fat")
        build.command(f"rc {first_boot}/select /root /n/9fat")
    selected_roots["build"] = "stable"
    with cpu("build") as build:
        build.command(". /usr/local/pkg/nix9/system; cat /cfg/nix9/files/version", "one")
        build.command("cat $nix9SystemRoot^-boot", systems["build"]["first"])
    print("PASS: authenticated CPU login, independent generations, reboot, GC retention and rollback", flush=True)
    print("PASS: versioned root publication, independent CPU upgrades, retained state and OS root rollback", flush=True)

    with cpu("build", medium=bad_medium, failure=r"mount: auth_proxy:"):
        pass
    identity = "/n/site/machines/build/usr/local/nix/state/machine-id"
    files.command("echo other > " + identity)
    with cpu("build", failure=r"nix9: network root: machine identity mismatch"):
        pass
    files.command("mv " + identity + " " + identity + ".saved")
    with cpu("build", failure=r"nix9: network root: machine state is not prepared"):
        pass
    files.command("echo build > " + identity + "; rm " + identity + ".saved")
    with cpu("build") as build:
        build.command(". /usr/local/pkg/nix9/system; cat /cfg/nix9/files/version", "one")
        build.command("nix-store --verify-path " + project_output)
    files.command("cat /usr/local/nix/state/machine-id", "files")
    files.command("cat /n/site/machines/batch/usr/local/nix/state/machine-id", "batch")
    files.child.sendline("fshalt")
    files.child.expect("done halting")
    files.crash()
    with cpu("build", failure=r"mount:.*(?:/root|boot)"):
        pass
    print("PASS: bad credentials and missing or mismatched state fail before Nix starts", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({"status": "passed", "machines": 4,
        "bootMediaBytes": sizes, "systems": systems, "nativeOutput": project_output, "roots": root_directories,
        "checks": ["authenticated-network-root", "no-local-os", "separate-state", "native-c-build",
                   "newns", "remote-login", "untrusted-service", "hostname-change", "reboot", "gc-retention", "rollback", "bad-key",
                   "missing-state", "wrong-identity", "root-provider-offline", "reproducible-root", "publish-once",
                   "partial-publication", "wrong-boot-medium", "root-upgrade", "mixed-root-versions", "root-rollback",
                   "no-private-root-copies"]}, indent=2) + "\n")
