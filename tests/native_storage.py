"""A separate auth server, CWFS volume, two CPU servers and a shared workspace."""

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

from guest import boot


ROOTS = "/usr/local/nix/state/gcroots"
PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"
NAMES = ("auth", "files", "build", "batch", "terminal")
BACKUPS = os.environ.get("NIX9_BACKUP_TEST") == "1"
if BACKUPS:
    NAMES += ("backup",)


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def rejected(guest, command, reason=None):
    result = guest.command("rc -c " + quote(command) + "; echo STORAGE-ERROR:$status")
    if (not re.search(r"(?m)^STORAGE-ERROR:.+", result) or "syntax error" in result
            or (reason and reason.lower() not in result.lower())):
        raise RuntimeError(f"operation was not rejected: {command}: {result}")
    return result


def stop(guest):
    guest.child.sendline("fshalt")
    guest.child.expect("done halting")
    guest.crash()


def listening(guest, port):
    for _ in range(30):
        table = guest.command("netstat -n")
        if re.search(r"(?m)^tcp\s+\d+\s+\S+\s+Listen\s+" + str(port) + r"\s", table):
            return
        time.sleep(0.2)
    raise RuntimeError(f"listener did not start: {table}")


def selection(guest, name):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command(f"cat {ROOTS}/machines/{name}/system"))
    if len(paths) != 1:
        raise RuntimeError("missing system selection")
    return paths[0]


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_STORAGE_TEST_STATE")
with ExitStack() as stack:
    work = Path(stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory()))
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("backups.nix" if BACKUPS else "storage.nix"), work / "storage.nix")
    (work / "cwfs.setup").write_text("service files\nconfig /adm/storage/config\n"
                                     "filsys main cw0fw1\nfilsys dump o\nream main\nend\n")
    (work / "project.nix").write_text("{ pkgs ? import <nix9> }: pkgs.mkDerivation {\n"
        "  name = \"storage-project\"; src = ./hello.c; buildCommand = ''\n"
        "    6c -o hello.6 $src\n    mkdir -p $out/bin\n    6l -o $out/bin/storage-project hello.6\n  '';\n}\n")
    (work / "hello.c").write_text('#include <u.h>\n#include <libc.h>\n'
                                  'void main(void) { print("storage-original\\n"); exits(nil); }\n')
    keys = {name: secrets.token_bytes(16) for name in ("files", "build", "batch", "glenda")}
    if BACKUPS:
        keys["backup"] = secrets.token_bytes(16)
    for name, key in keys.items():
        roles = ["client"] if name == "glenda" else ["server", "speakfor"] if name in ("build", "batch") else ["server"]
        for suffix, data in (("keys", "".join(f"key proto=dp9ik dom=nix9.storage user={name} role={role} "
                                f"!hex={key.hex()} !password=______\n" for role in roles).encode()), ("aes", key)):
            file = work / (name + "." + suffix)
            file.write_bytes(data)
            file.chmod(0o600)
    for name in NAMES:
        fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
                  (b"nix9.storage" if name == "auth" else b"bootstrap.invalid").ljust(48, b"\0"), secrets.token_bytes(16))
        file = work / (name + ".nvram")
        file.write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
        file.chmod(0o600)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    http = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
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
    endpoints = [("10.0.2.100", 567), ("10.0.2.101", 564), ("10.0.2.102", 17019), ("10.0.2.102", 17020), ("10.0.2.103", 17019)]
    if BACKUPS:
        endpoints.append(("10.0.2.105", 17021))
    for address, port in endpoints:
        reservation = stack.enter_context(socket.socket())
        reservation.bind(("127.0.0.1", 0))
        host = reservation.getsockname()[1]
        peers.append((address, port, host))
        reservations[host] = reservation
    qemu_img = str(Path(qemu).with_name("qemu-img"))
    foundation = work / "bootstrap.qcow2"
    if foundation.exists():
        raise RuntimeError(f"refusing to overwrite an existing VM: {foundation}")

    def disk(path, backing):
        subprocess.run([qemu_img, "create", "-f", "qcow2", "-F", "qcow2", "-b", str(Path(backing).resolve()), str(path)], check=True)

    disk(foundation, image)
    with boot(qemu, foundation, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix-build '<nix9>' -A cwfs -A auth -A rcpu -A ndb -A namespaceTools "
                      + ("-A diskArchive " if BACKUPS else "")
                      + "--out-link " + ROOTS + "/storage-tools")
    disks, systems = {}, {}
    for name in NAMES:
        disks[name] = work / (name + ".qcow2")
        disk(disks[name], foundation)
        with boot(qemu, disks[name], snapshot=False) as guest:
            guest.child.timeout = 900
            guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init " + name)
            download(guest, "storage.nix")
            for configuration in (name, "noDumps"):
                guest.command(f"echo '(import ./storage.nix {{}}).{configuration}' > /tmp/{configuration}.nix")
            download(guest, name + ".nvram", "/tmp/boot.nvram", private=True)
            guest.command("dd -if /tmp/boot.nvram -of /dev/sdF0/nvram -bs 126 -count 1")
            if name == "auth":
                guest.command("rm -f /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                for identity in keys:
                    download(guest, identity + ".aes", private=True)
                    guest.command(f"mkdir /mnt/keys/{identity}; cp /tmp/{identity}.aes /mnt/keys/{identity}/aeskey")
                if BACKUPS:
                    download(guest, "glenda.keys", "/adm/scheduler.keys", private=True)
            if name == "backup":
                download(guest, "backup.keys", "/adm/backup.keys", private=True)
            if name in ("files", "build", "batch"):
                download(guest, name + ".keys", "/adm/" + ("files" if name == "files" else "cpu") + ".keys", private=True)
            if name != "terminal":
                guest.command(f"mkdir -p /cfg/{name}/service")
            else:
                download(guest, "glenda.keys", "/adm/terminal.keys", private=True)
                guest.command("echo 'cat /adm/terminal.keys > /mnt/factotum/ctl' > /rc/bin/termrc.local")
                download(guest, "project.nix")
                download(guest, "hello.c")
            if name == "build":
                guest.command("echo tls-tools-ready > /usr/glenda/stock-marker")
            if name == "files":
                guest.command("mkdir /adm/storage; chmod 700 /adm/storage")
                for volume, offset in (("config", 0), ("cache", 4095), ("worm", 8191)):
                    guest.command(f"dd -if /dev/zero -of /adm/storage/{volume} -bs 16384 -count 1 -oseek {offset}; chmod 600 /adm/storage/{volume}")
                guest.command("cp /adm/storage/config /tmp/blank-config")
                rejected(guest, "nix9-rebuild switch /tmp/files.nix", "not a provisioned cwfs64x configuration")
                guest.command("cmp /adm/storage/config /tmp/blank-config; test ! -e " + ROOTS + "/machines/files/system")
                download(guest, "cwfs.setup")
                guest.command("echo 'w0 /adm/storage/cache' > /tmp/devices; echo 'w1 /adm/storage/worm' >> /tmp/devices")
                guest.command(f"cwfs=`{{cat {ROOTS}/storage-tools}}; fsmempercent=5 $cwfs/bin/cwfs64x "
                              "-c -f /adm/storage/config -m /tmp/devices -n cwfs-provision -a tcp!*!564 < /tmp/cwfs.setup")
                for command in ("users default", "create /adm adm adm 775 d", "create /adm/users adm adm 664", "create /usr adm adm 775 d",
                                "newuser glenda", "create /projects glenda glenda 750 d", "sync"):
                    guest.command("echo " + quote(command) + " >> /srv/cwfs-provision.cmd")
                guest.command("sleep 1; mount -nc /srv/cwfs-provision /n/provision")
                guest.command("grep glenda /n/provision/adm/users")
                guest.command("unmount /n/provision; echo halt >> /srv/cwfs-provision.cmd")
                guest.command("while(test -e /srv/cwfs-provision.cmd) sleep 1; status=''")
                guest.command("chmod 640 /adm/files.keys")
                rejected(guest, "nix9-rebuild switch /tmp/files.nix", "unsafe permissions")
                guest.command("chmod 600 /adm/files.keys")
            guest.command(f"nix9-rebuild switch /tmp/{name}.nix")
            systems[name] = selection(guest, name)
            if name != "terminal":
                guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    if BACKUPS:
        # The replacement has its own empty, cleanly halted CWFS volume.
        shutil.copyfile(disks["files"], work / "replacement.qcow2")

    @contextmanager
    def start(name):
        address = {"auth": "10.0.2.100", "files": "10.0.2.101", "build": "10.0.2.102", "batch": "10.0.2.103", "backup": "10.0.2.105"}.get(name)
        forwards = [(host, port) for peer, port, host in peers if peer == address]
        for host, _ in forwards:
            reservations[host].close()
        with boot(qemu, disks[name], snapshot=False, configure_network=False,
                  cpu=name != "terminal", prompt=PROMPT, guest_forwards=peers,
                  forward_ports=forwards, network_options=("restrict=on",)) as guest:
            guest.child.timeout = 180
            guest.command(". /usr/local/pkg/nix9/activate")
            yield guest

    # Storage boots before authentication and does not make an authenticated mount at boot.
    files = stack.enter_context(start("files"))
    listening(files, 564)
    files.command("ls -ld /srv/cwfs-nix9.cmd | grep -s '^-[-l]rw------- '")
    auth = stack.enter_context(start("auth"))
    listening(auth, 567)
    builders = {name: stack.enter_context(start(name)) for name in ("build", "batch")}
    for guest in builders.values():
        listening(guest, 17019)
    backup = stack.enter_context(start("backup")) if BACKUPS else None
    if BACKUPS:
        listening(backup, 17021)
    terminal = stack.enter_context(start("terminal"))
    terminal.command(". /usr/local/pkg/nix9/system")
    terminal.command("cat /n/tools/stock-marker", "tls-tools-ready")
    terminal.command("cp /tmp/project.nix /usr/glenda/work/default.nix")
    terminal.command("cp /tmp/hello.c /usr/glenda/work/hello.c")
    if BACKUPS:
        # Fail before writing anything when no completed source snapshot exists.
        rejected(terminal, "rcpu -h build -c 'rc $nix9System/services/backups/projects/run'", "no completed CWFS snapshot")
        backup.command("test ! -e /usr/glenda/archives/projects")

    def remote(name, command, expected=None):
        return terminal.command("rcpu -h " + name + " -c " + quote(command), expected)

    def compile_on(name):
        remote(name, "nix-build /usr/glenda/work --out-link " + ROOTS + "/workspace")
        paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", builders[name].command("cat " + ROOTS + "/workspace"))
        if len(paths) != 1:
            raise RuntimeError("missing workspace build")
        remote(name, paths[0] + "/bin/storage-project", "storage-original")
        return paths[0]

    built = {"build": compile_on("build")}
    builders["batch"].command("test ! -e " + built["build"])
    built["batch"] = compile_on("batch")
    if built["build"] != built["batch"]:
        raise RuntimeError("the two local stores produced different workspace outputs")
    records = auth.command("cat /sys/log/auth")
    for name in builders:
        if not re.search(r"tr-ok glenda@" + name + r".* -> glenda@files", records):
            raise RuntimeError("missing delegated filesystem authentication from " + name)
    print("PASS: storage boots independently, native authenticated main mount, shared workspace and builds on two CPU servers", flush=True)

    files.command("echo dump >> /srv/cwfs-nix9.cmd")
    deadline = time.monotonic() + 30
    while True:
        listing = terminal.command("ls -d /n/history/*/* >[2]/dev/null; status=''")
        snapshots = re.findall(r"(?m)^/n/history/[0-9]{4}/[0-9]+$", listing)
        if snapshots:
            snapshot = snapshots[-1]
            break
        if time.monotonic() > deadline:
            raise RuntimeError("CWFS dump did not appear")
        time.sleep(0.2)
    terminal.command("cmp " + snapshot + "/projects/hello.c /usr/glenda/work/hello.c")
    rejected(terminal, "echo forbidden > " + snapshot + "/projects/hello.c", "read only")
    terminal.command("rm /usr/glenda/work/hello.c")
    for name in builders:
        remote(name, "test ! -e /usr/glenda/work/hello.c")
    terminal.command("cp " + snapshot + "/projects/hello.c /usr/glenda/work/hello.c")
    for name in builders:
        if compile_on(name) != built[name]:
            raise RuntimeError("restoration changed the workspace output")
    remote("build", "cmp " + snapshot + "/projects/hello.c /usr/glenda/work/hello.c")
    print("PASS: read-only historical dump, deleted-file recovery and restored builds from both CPU servers", flush=True)

    disabled = None
    if not BACKUPS:
        files.command("nix9-rebuild switch /tmp/noDumps.nix")
        disabled = selection(files, "files")
        remote("build", "cat /usr/glenda/work/hello.c")
        stop(files)
        files = stack.enter_context(start("files"))
        listening(files, 564)
        for name in builders:
            if compile_on(name) != built[name]:
                raise RuntimeError("reboot changed the workspace output")
        remote("build", "cmp " + snapshot + "/projects/hello.c /usr/glenda/work/hello.c")
        files.command("nix9-rebuild rollback")
        if selection(files, "files") != systems["files"]:
            raise RuntimeError("rollback did not restore the filesystem generation")
        stop(files)
        files = stack.enter_context(start("files"))
        listening(files, 564)
        remote("batch", "cat /usr/glenda/work/hello.c")
        print("PASS: native fshalt, persistent data and snapshots, new-session reconnection, snapshot policy selection and rollback", flush=True)

    backup_results = None
    if BACKUPS:
        from native_backups import check_backups
        backup_results = check_backups(
            work=work, stack=stack, terminal=terminal, auth=auth, files=files,
            backup=backup, builders=builders, systems=systems, snapshot=snapshot,
            start=start, stop=stop, built=built, disks=disks,
            listening=listening, rejected=rejected,
        )

    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "machines": len(NAMES), "fileServerBoots": 2 if BACKUPS else 3, "systems": systems,
        "backups": backup_results,
        "noDumpsSystem": disabled, "builds": built, "snapshot": snapshot,
        "checks": ["unformatted-volume-rejected-without-writes", "private-server-key", "independent-storage-boot",
                   "native-9p-authentication", "tls-export-regression", "delegated-two-cpu-builds", "shared-workspace", "read-only-history",
                   "file-restoration", "native-shutdown"] + ([] if BACKUPS else [
                   "persistent-data", "provider-reboot", "policy-selection", "rollback"]),
    }, indent=2) + "\n")
