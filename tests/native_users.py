"""Shared development on two CPUs, protected machine stores and CWFS accounts."""

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
from user_development import check_development, check_profiles


ROOTS = "/usr/local/nix/state/gcroots"
PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"
CPUS = ("build", "batch")


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def path(guest, command):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(command))
    if len(paths) != 1:
        raise RuntimeError(f"expected one store path: {command}: {paths}")
    return paths[0]


def rejected(guest, command, reason):
    result = guest.command("rc -c " + quote(command) + "; echo USER-ERROR:$status")
    if not re.search(r"(?m)^USER-ERROR:.+", result) or reason not in result or "syntax error" in result:
        raise RuntimeError(f"unexpected rejection: {command}: {result}")


def stop(guest):
    guest.child.sendline("fshalt")
    guest.child.expect("done halting")
    guest.crash()


def listening(guest, port):
    for _ in range(40):
        result = guest.command(f"netstat -n | grep -s 'Listen *{port} '; echo USER-WAIT:$status")
        if re.search(r"(?m)^USER-WAIT:$", result):
            return
        time.sleep(0.2)
    raise RuntimeError(f"listener unavailable: {port}")


def nvram(key):
    fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
              b"nix9.netroot".ljust(48, b"\0"), key)
    return b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields)


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_USERS_TEST_STATE")
with ExitStack() as stack:
    work = Path(stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())).resolve()
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("accounts.nix"), work / "accounts.nix")
    shutil.copyfile(Path(__file__).with_name("user-development.rc"), work / "user-development.rc")
    (work / "cwfs.setup").write_text("service files\nconfig /adm/storage/config\n"
                                    "filsys main cw0fw1\nfilsys dump o\nream main\nend\n")
    keys = {name: secrets.token_bytes(16) for name in ("glenda", "alice", "bob", "files", *CPUS)}
    for name, key in keys.items():
        roles = ("server", "speakfor") if name in CPUS else ("server",) if name == "files" else ("client",)
        for suffix, data in (("keys", "".join(f"key proto=dp9ik dom=nix9.netroot user={name} role={role} "
                f"!hex={key.hex()} !password=______\n" for role in roles).encode()), ("aes", key)):
            file = work / f"{name}.{suffix}"
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
    for address, port in (("10.0.2.100", 567), ("10.0.2.101", 564), ("10.0.2.102", 17019),
                          ("10.0.2.103", 17019), ("10.0.2.100", 5356)):
        reservation = stack.enter_context(socket.socket())
        reservation.bind(("127.0.0.1", 0))
        host = reservation.getsockname()[1]
        peers.append((address, port, host))
        reservations[host] = reservation
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
        download(guest, "bootstrap.tar")
        guest.command("cd / && tar xf /tmp/bootstrap.tar && rm /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix-build '<nix9>' -A cwfs -A auth -A rcpu -A ndb --out-link " + ROOTS + "/user-tools")

    drives = []
    for name, size in (("cache", 3), ("worm", 8)):
        volume = work / (name + ".raw")
        with volume.open("xb") as file:
            file.truncate(size * 1024**3)
        drives.extend(("-drive", f"file={volume},format=raw,if=virtio"))
    disks, systems, bundles = {}, {}, {}
    for name in ("auth", "files"):
        disks[name] = work / (name + ".qcow2")
        disk(disks[name], foundation)
        with boot(qemu, disks[name], snapshot=False, qemu_options=drives if name == "files" else ()) as guest:
            guest.child.timeout = 1200
            guest.command(". /usr/local/pkg/nix9/activate && nix9 init " + name)
            download(guest, "server.nvram", "/tmp/server.nvram", private=True)
            guest.command("dd -if /tmp/server.nvram -of /dev/sdF0/nvram -bs 126 -count 1")
            download(guest, "accounts.nix")
            guest.command(f"mkdir -p /cfg/{name}/service")
            if name == "auth":
                guest.command("rm /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                for identity in keys:
                    download(guest, identity + ".aes", private=True)
                    guest.command(f"mkdir /mnt/keys/{identity}; cp /tmp/{identity}.aes /mnt/keys/{identity}/aeskey")
                guest.command("mkdir /mnt/keys/empty")
                for identity in ("glenda", "alice", "bob"):
                    download(guest, identity + ".keys", f"/adm/{identity}.keys", private=True)
                for attribute, reason in (("missingKey", "missing needs"), ("emptyKey", "empty has no")):
                    candidate = path(guest, f"nix-build /tmp/accounts.nix -A {attribute} --no-out-link")
                    rejected(guest, "nix9 check " + candidate, reason)
                candidate = path(guest, "nix-build /tmp/accounts.nix -A first.systems.auth --no-out-link")
                guest.command("echo disabled > /mnt/keys/bob/status")
                rejected(guest, "nix9 check " + candidate, "bob needs")
                guest.command("echo ok > /mnt/keys/bob/status")
                guest.command("echo 1 > /mnt/keys/bob/expire")
                rejected(guest, "nix9 check " + candidate, "bob needs")
                guest.command("echo never > /mnt/keys/bob/expire")
            else:
                download(guest, "files.keys", "/adm/files.keys", private=True)
                guest.command("mkdir /adm/storage; chmod 700 /adm/storage")
                guest.command("dd -if /dev/zero -of /adm/storage/config -bs 16384 -count 1; chmod 600 /adm/storage/config")
                download(guest, "cwfs.setup")
                guest.command("echo 'w0 /dev/sdG0/data' > /tmp/devices; echo 'w1 /dev/sdH0/data' >> /tmp/devices")
                guest.command(f"cwfs=`{{cat {ROOTS}/user-tools}}; fsmempercent=5 $cwfs/bin/cwfs64x "
                              "-c -f /adm/storage/config -m /tmp/devices -n provision < /tmp/cwfs.setup")
                for command in ("users default", "create /adm adm adm 775 d", "create /adm/users adm adm 664",
                                "create /usr adm adm 775 d", "newuser glenda", "create /systems glenda glenda 775 d",
                                "create /machines glenda glenda 775 d"):
                    guest.command("echo " + quote(command) + " >> /srv/provision.cmd")
                guest.command("echo halt >> /srv/provision.cmd; while(test -e /srv/provision.cmd) sleep 1; status=''")
                for version in ("first", "second", "third"):
                    bundles[version] = path(guest, f"nix-build /tmp/accounts.nix -A {version}.build --no-out-link")
                for machine in ("files", *CPUS):
                    systems[machine] = {version: path(guest, f"cat {bundle}/systems/{machine}") for version, bundle in bundles.items()}
            candidate = path(guest, f"nix-build /tmp/accounts.nix -A first.systems.{name} --no-out-link")
            guest.command("nix9 select " + candidate)
            guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    @contextmanager
    def server(name):
        address, port, _ = peers[0 if name == "auth" else 1]
        forwards = [(host, target) for peer, target, host in peers if peer == address and target != 5356]
        for host, _ in forwards:
            reservations[host].close()
        with boot(qemu, disks[name], snapshot=False, cpu=True, configure_network=False, prompt=PROMPT,
                  forward_ports=forwards, guest_forwards=peers, network_options=("restrict=on",),
                  qemu_options=drives if name == "files" else ()) as guest:
            guest.child.timeout = 1200
            guest.command(". /usr/local/pkg/nix9/system")
            listening(guest, port)
            try:
                yield guest
            finally:
                if not guest.crashed and guest.child.isalive():
                    guest.child.timeout = 30
                    try:
                        stop(guest)
                    except Exception as error:
                        print(f"test VM {name} did not halt cleanly ({type(error).__name__})", file=sys.stderr)

    auth = stack.enter_context(server("auth"))
    files = stack.enter_context(server("files"))
    for identity in ("glenda", "alice", "bob"):
        auth.command(f"cat /adm/{identity}.keys > /mnt/factotum/ctl")
    auth.command("ls -ld /srv/nix9-keys | grep -s '^-[-l]rw------- '")
    auth.command("mount -c /srv/nix9-keys /mnt/keys")
    files.command("webfs")
    base = f"http://10.0.2.104:{http.server_port}"
    download(files, "glenda.keys", "/tmp/client.keys", private=True)
    files.command("cat /tmp/client.keys > /mnt/factotum/ctl && mount -c /srv/cwfs-nix9 /n/site main")
    files.command("cat /n/site/adm/users | grep '^1010:alice:alice:$'")
    files.command("cat /n/site/adm/users | grep '^1012:project:alice:alice,bob$'")
    root = path(files, f"cat {bundles['first']}/roots/stable")
    files.command(f"rc {root}/publish /n/site")
    download(files, "bootstrap.tar", "/tmp/node-bootstrap.tar")
    cpu_networks = {}
    for name, address in zip(CPUS, ("10.0.2.102", "10.0.2.103")):
        artifact = path(files, f"cat {bundles['first']}/boot/{name}/path")
        files.command(f"rc {artifact}/prepare /n/site /tmp/node-bootstrap.tar")
        directory = "/n/site/machines/" + name
        download(files, name + ".keys", directory + "/adm/cpu.keys", private=True)
        download(files, "user-development.rc", directory + "/usr/user-development.rc")
        files.command("chmod 444 " + directory + "/usr/user-development.rc")
        files.command(f"echo {systems[name]['first']} > {directory}/tmp/system-path")
        files.command(f"nix-store --export `{{nix-store -qR {systems[name]['first']}}} > {directory}/tmp/system.export")
        settings = files.command("cat " + artifact + "/plan9.ini")
        configuration = "\n".join(line for line in settings.splitlines() if re.match(r"^[a-z0-9]+=", line)) + "\n"
        disks[name] = work / (name + ".qcow2")
        boot_medium(qemu, image, disks[name], configuration, nvram(keys["glenda"]))
        network = ("restrict=on",)
        for peer, port, host in peers:
            if peer == address:
                reservations[host].close()
                network += (f"hostfwd=tcp:127.0.0.1:{host}-{peer}:{port}",)
        cpu_networks[name] = network
        with boot(qemu, disks[name], snapshot=False, cpu=True, configure_network=False, prompt=PROMPT,
                  boot_prompt=False, guest_forwards=peers, network_options=network) as cpu:
            cpu.child.timeout = 1200
            cpu.command(". /usr/local/pkg/nix9/activate && nix-store --import < /tmp/system.export")
            cpu.command("nix9 select `{cat /tmp/system-path}")

    @contextmanager
    def start_cpu(name):
        with boot(qemu, disks[name], snapshot=False, cpu=True, configure_network=False,
                  prompt=PROMPT, boot_prompt=False, guest_forwards=peers, network_options=cpu_networks[name]) as guest:
            guest.child.timeout = 1200
            guest.command(". /usr/local/pkg/nix9/system")
            listening(guest, 17019)
            listening(guest, 17051)
            try:
                yield guest
            finally:
                if not guest.crashed and guest.child.isalive():
                    guest.child.timeout = 30
                    try:
                        stop(guest)
                    except Exception as error:
                        print(f"test VM {name} did not halt cleanly ({type(error).__name__})", file=sys.stderr)

    cpus = {name: stack.enter_context(start_cpu(name)) for name in CPUS}

    def restart_files():
        # Stop the CPU while its root provider is still reachable.
        for cpu in cpus.values():
            stop(cpu)
        stop(files)
        provider = stack.enter_context(server("files"))
        consumers = {name: stack.enter_context(start_cpu(name)) for name in CPUS}
        return provider, consumers

    def remote(user, command, expected=None, machine="build"):
        return auth.command(f"rcpu -u {user} -h {machine} -c " + quote(command), expected)

    remote("alice", f"test -r {ROOTS}/machines/build/system && test ! -w {ROOTS}/machines/build/system")
    remote("alice", "echo $user; echo alice-private > /usr/alice/private; echo shared > /n/projects/message; chmod 660 /n/projects/message", "alice")
    remote("bob", "echo $user; cat /n/projects/message; echo bob-private > /usr/bob/private", "bob")
    remote("alice", "cat /usr/alice/private", "alice-private")
    remote("bob", "cat /usr/bob/private", "bob-private")
    rejected(auth, "rcpu -u bob -h build -c 'cat /usr/alice/private'", "")
    rejected(auth, "rcpu -u alice -h build -c 'cat /usr/bob/private'", "")
    remote("bob", "echo bob >> /n/projects/message")
    remote("alice", "grep bob /n/projects/message", "bob")
    auth.command("echo disabled > /mnt/keys/bob/status")
    rejected(auth, "rcpu -u bob -h build -c 'echo unexpected'", "")
    auth.command("echo ok > /mnt/keys/bob/status")
    remote("bob", "cat /usr/bob/private", "bob-private")
    print("PASS: two authenticated CPU users, shared homes, group access and private home permissions", flush=True)

    for name in CPUS:
        for user in ("alice", "bob"):
            remote(user, f"cat /usr/{user}/private", user + "-private", machine=name)
            remote(user, "fortune > $home/fortune && test -s $home/fortune", machine=name)
            remote(user, "test ! -w /usr/local/nix/state/db/db.sqlite", machine=name)
    remote("alice", "mkdir -p /n/projects/hello && cp $nix9/packages/examples/workstation/project/* /n/projects/hello/")
    remote("alice", "chmod 770 /n/projects/hello && chmod 660 /n/projects/hello/*")

    remote("alice", "echo alice > /n/projects/hello/participants && chmod 660 /n/projects/hello/participants")
    remote("bob", "echo bob >> /n/projects/hello/participants", machine="batch")
    remote("alice", "cat /n/projects/hello/participants", "bob")
    print("PASS: both CPUs expose system packages and shared sources while protecting machine stores", flush=True)
    environments = check_development(auth, cpus, remote)

    updated = path(files, "nix-build /tmp/accounts.nix -A updatedCpu --no-out-link")
    # The update adds a literal file; its dependencies are already on the CPU.
    files.command(f"nix-store --export {updated} > /n/site/machines/build/tmp/update.export")
    cpus["build"].command("nix-store --import < /tmp/update.export")
    cpus["build"].command("nix9 select " + updated)
    stop(cpus["build"])
    cpus["build"] = stack.enter_context(start_cpu("build"))
    remote("alice", "cat /cfg/nix9/files/user-workflow", "updated")
    cpus["batch"].command(f"~ `{{cat {ROOTS}/machines/batch/system}} {systems['batch']['first']}")
    remote("bob", "fortune > $home/fortune && test -s $home/fortune", machine="batch")
    remote("alice", "cat /usr/alice/private", "alice-private")
    remote("alice", "cat /n/projects/hello/participants", "bob")
    check_profiles(remote, environments)
    print("PASS: updating and rebooting one CPU preserves the other CPU, shared homes and project edits", flush=True)

    cpus["build"].command("nix9-rebuild rollback")
    stop(cpus["build"])
    cpus["build"] = stack.enter_context(start_cpu("build"))
    cpus["build"].command(f"~ `{{cat {ROOTS}/machines/build/system}} {systems['build']['first']}")
    for cpu in cpus.values():
        cpu.command("nix-store --gc")
    check_profiles(remote, environments)
    print("PASS: CPU system rollback and GC retain both users' development profiles", flush=True)

    files.command("cp /n/site/adm/users /tmp/users-before-check")
    for attribute, reason in (("conflicting", "existing name has another ID"), ("occupied", "ID belongs to another name"),
                              ("unknownMember", "unknown group member"), ("blockedDirectory", "not a regular directory")):
        if attribute == "blockedDirectory":
            remote("alice", "echo unchanged > /n/projects/plain")
        candidate = path(files, f"nix-build /tmp/accounts.nix -A {attribute} --no-out-link")
        rejected(files, "nix9 check " + candidate, reason)
    files.command("cmp /n/site/adm/users /tmp/users-before-check && test ! -e /n/site/usr/carol && grep '^1010:alice:' /n/site/adm/users")
    files.command("nix9 select " + systems["files"]["second"])
    remote("bob", "cat /n/projects/message")
    files, cpus = restart_files()
    rejected(auth, "rcpu -u bob -h build -c 'cat /n/projects/message'", "")
    remote("bob", "cat /usr/bob/private", "bob-private")
    remote("alice", "cat /n/projects/message")
    check_profiles(remote, environments)
    print("PASS: read-only preflight rejects ID and directory conflicts; group changes apply at file-server boot", flush=True)

    files.command("nix9 select " + systems["files"]["third"])
    files, cpus = restart_files()
    remote("bob", "cat /usr/bob/private", "bob-private")
    files.command("nix9-rebuild rollback")
    files.command("nix9-rebuild rollback")
    if path(files, f"cat {ROOTS}/machines/files/system") != systems["files"]["first"]:
        raise RuntimeError("rollback did not restore the initial account declaration")
    files, cpus = restart_files()
    remote("bob", "cat /n/projects/message")
    remote("alice", "cat /usr/alice/private", "alice-private")
    remote("alice", "grep '^1013:carol:carol:$' /root/adm/users", "1013:carol:carol:")
    check_profiles(remote, environments)
    records = auth.command("cat /sys/log/auth")
    for user in ("alice", "bob"):
        if not re.search(r"tr-ok " + user + r"@glenda.* -> " + user + r"@glenda", records):
            raise RuntimeError("missing delegated filesystem authentication for " + user)
    print("PASS: undeclared accounts and homes survive selection and rollback; declared memberships are restored", flush=True)
    for cpu in cpus.values():
        stop(cpu)
    stop(files)
    stop(auth)
    Path(output).mkdir(parents=True, exist_ok=True)
    Path(output, "results.json").write_text(json.dumps({
        "status": "passed", "machines": 4, "users": ["alice", "bob"], "fileServerBoots": 4,
        "cpuBoots": {"build": 7, "batch": 5},
        "checks": ["missing-keys", "empty-keys", "disabled-keys", "expired-keys", "two-user-login",
                   "two-cpu-homes", "system-packages", "machine-store-permissions", "shared-source-editing", "independent-cpu-update",
                   "private-homes", "shared-project", "id-conflicts", "unknown-members", "directory-preflight",
                   "boot-policy", "group-revocation", "undeclared-accounts", "rollback", "delegated-authentication",
                   "shared-store-cpu-logins", "shared-build-reuse", "independent-user-profiles", "user-profile-rollback",
                   "independent-machine-roots", "concurrent-development-shells", "shell-native-c", "shell-caller-identity",
                   "shell-gc", "logout-root-cleanup", "cpu-rollback", "profiles-across-provider-reboots"],
    }, indent=2) + "\n")
