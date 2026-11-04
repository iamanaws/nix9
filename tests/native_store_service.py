"""Managed shared-store startup, login defaults, policy changes and rollback."""

import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time

from guest import boot, files_guest


ROOT = "/usr/local/nix/state/gcroots/machines/store/system"
PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def login(guest, user, command, expected=None):
    # Real login hook, without setting NIX_REMOTE or sourcing a test activation.
    line = "/amd64/bin/auth/as " + user + " /bin/rc -el -c " + quote(command)
    if len(line) > 220:
        guest.command("echo -n > /tmp/login-command; chmod 644 /tmp/login-command")
        for offset in range(0, len(command), 100):
            guest.command("echo -n " + quote(command[offset:offset + 100]) + " >> /tmp/login-command")
        line = "/amd64/bin/auth/as " + user + " /bin/rc -el -c '. /tmp/login-command'"
    return guest.command(line, expected)


def denied(guest, user, prefix=""):
    result = login(guest, user, prefix + "nix-store --roots-dir || echo STORE-ERROR:$status")
    if not re.search(r"(?m)^STORE-ERROR:.+", result) or "cannot open connection" not in result:
        raise RuntimeError("store policy did not reject the user: " + result)


def listening(guest, port):
    deadline = time.monotonic() + 20
    while True:
        table = guest.command("netstat -n")
        if re.search(r"(?m)^tcp\s+\d+\s+\S+\s+Listen\s+" + str(port) + r"\s", table):
            return
        if time.monotonic() >= deadline:
            guest.command("cat /sys/log/nix9-store; ps")
            raise RuntimeError("store listener did not start: " + table)
        time.sleep(0.1)


def check_profile(guest, user, version):
    login(guest, user, "roots=`{nix-store --roots-dir}; "
          ". $nix9/packages/profile $roots/environment; shared-choice", version)


qemu, image, archive, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    disk = work / "store-service.qcow2"
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2", "-F", "qcow2",
                    "-b", str(Path(image).resolve()), str(disk)], check=True)
    fixtures = {"bootstrap.tar": archive}
    for name in ("store-service.nix", "shared-store.nix"):
        fixtures[name] = Path(__file__).with_name(name)
    for user in ("nixhost", "alice", "bob"):
        key = secrets.token_bytes(16)
        role = "server" if user == "nixhost" else "client"
        owner = "glenda" if user == "nixhost" else user
        command = (f"key proto=dp9ik dom=nix9.shared user={user} role={role} owner={owner} "
                   f"!hex={key.hex()} !password=______\n")
        for suffix, data in (("aes", key), ("keys", command.encode())):
            path = work / (user + "." + suffix)
            path.write_bytes(data)
            path.chmod(0o600)
            fixtures[path.name] = path
    fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
              b"nix9.shared".ljust(48, b"\0"), secrets.token_bytes(16))
    nvram = work / "nvram"
    nvram.write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
    nvram.chmod(0o600)
    fixtures["nvram"] = nvram
    with files_guest(qemu, disk, fixtures, snapshot=False, transfer_timeout=1200) as guest:
        guest.child.timeout = 900
        guest.command("cd / && tar xf /tmp/bootstrap.tar && rm /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate; nix9 init store")
        guest.command("chmod 777 /tmp")
        for user in ("alice", "bob"):
            guest.command("echo 'newuser " + user + "' >> /srv/hjfs.cmd")
            guest.command(f"auth/as {user} /bin/mkdir -p /usr/{user}/tmp")
        guest.command("echo disallow >> /srv/hjfs.cmd; sleep 1; echo")
        guest.command("nix-build '<nix9>' -A auth --out-link /usr/local/nix/state/gcroots/test-auth")
        guest.command("authpkg=`{cat /usr/local/nix/state/gcroots/test-auth}")
        guest.command("dd -if /tmp/nvram -of /dev/sdF0/nvram -bs 126 -count 1; rm /tmp/nvram")
        guest.command("$authpkg/bin/auth/keyfs -s test-keys -m /mnt/keys /adm/shared.keys </dev/null")
        for user in ("nixhost", "alice", "bob"):
            guest.command(f"mkdir /mnt/keys/{user}; cp /tmp/{user}.aes /mnt/keys/{user}/aeskey; rm /tmp/{user}.aes")
        guest.command("chmod 600 /adm/shared.keys")
        guest.command("cp /tmp/nixhost.keys /adm/nix-store.keys; chmod 600 /adm/nix-store.keys")
        # Provisioned credentials, loaded by the existing native boot hook.
        for user in ("alice", "bob"):
            guest.command(f"cp /tmp/{user}.keys /adm/{user}.keys; chmod 600 /adm/{user}.keys")
            guest.command(f"echo 'cat /adm/{user}.keys > /mnt/factotum/ctl' >> /rc/bin/cpurc.local")
        guest.command("rm /tmp/*.keys")
        guest.command("cp /tmp/shared-store.nix /usr/shared-store.nix; chmod 444 /usr/shared-store.nix")
        for name in ("initial", "moved", "disabled"):
            guest.command(f"echo '(import ./store-service.nix {{}}).{name}' > /tmp/{name}.nix")
        guest.command("nix9-rebuild build /tmp/initial.nix")
        guest.command("initial=`{cat " + ROOT + "-build}")
        guest.command("chmod 644 /adm/nix-store.keys")
        result = guest.command("nix9 check $initial; echo STORE-ERROR:$status")
        if "unsafe permissions" not in result or not re.search(r"(?m)^STORE-ERROR:.+", result):
            raise RuntimeError("unsafe runtime key file passed the system check")
        guest.command("chmod 600 /adm/nix-store.keys")
        guest.command("mkdir -p /cfg/store/service; echo '#!/bin/rc' > /cfg/store/service/tcp17051")
        result = guest.command("nix9 check $initial; echo STORE-ERROR:$status")
        if "already owns tcp17051" not in result or not re.search(r"(?m)^STORE-ERROR:.+", result):
            raise RuntimeError("manual listener collision passed the system check")
        guest.command("rm /cfg/store/service/tcp17051; nix9 select $initial")
        guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; "
                      "echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")
    print("PASS: private keys and manual listener collisions checked before selection", flush=True)

    def start():
        return boot(qemu, disk, snapshot=False, configure_network=False, cpu=True, prompt=PROMPT,
                    network_options=("restrict=on",))

    with start() as guest:
        guest.child.timeout = 900
        listening(guest, 17051)
        guest.command(". /usr/local/pkg/nix9/system")
        guest.command("echo $NIX_REMOTE", "local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log")
        guest.command("nix9 status --health", "store health nix/daemon ok")
        for user in ("alice", "bob"):
            login(guest, user, "echo $NIX_REMOTE", "daemon?address=tcp!127.0.0.1!17051&key-pattern=user=" + user)
            login(guest, user, "test ! -w /usr/local/nix/store && test ! -w /usr/local/nix/state/db/db.sqlite")
            login(guest, user, "nix-build /usr/shared-store.nix -A envOne; roots=`{nix-store --roots-dir}; "
                  "nix-profile $roots/environment set `{cat $roots/result}")
            check_profile(guest, user, "one")
        login(guest, "alice", "user=bob; . /usr/local/pkg/nix9/system; nix-store --roots-dir",
              "/usr/local/nix/state/gcroots/per-user/alice")
        login(guest, "alice", "nix-build /usr/shared-store.nix -A envTwo; roots=`{nix-store --roots-dir}; "
              "nix-profile $roots/environment set `{cat $roots/result}")
        guest.command("nix9-rebuild switch /tmp/moved.nix")
        check_profile(guest, "alice", "two")
        check_profile(guest, "bob", "one")
        login(guest, "alice", "echo $NIX_REMOTE", "daemon?address=tcp!127.0.0.1!17051&key-pattern=user=alice")
    print("PASS: login selects the shared service, owner stays local, selection keeps booted policy and port", flush=True)

    with start() as guest:
        guest.child.timeout = 600
        listening(guest, 17052)
        guest.command(". /usr/local/pkg/nix9/system")
        login(guest, "bob", "echo $NIX_REMOTE", "daemon?address=tcp!127.0.0.1!17052&key-pattern=user=bob")
        check_profile(guest, "bob", "one")
        denied(guest, "alice")
        denied(guest, "alice", "NIX_CONFIG='allowed-users = *'; ")
        guest.command("grep 'allowed-users = bob' /cfg/nix9/files/nix.conf")
        guest.command("nix9-rebuild rollback")
        denied(guest, "alice")
        check_profile(guest, "bob", "one")
    print("PASS: new port and restricted policy apply after reboot; rollback waits for reboot", flush=True)

    with start() as guest:
        guest.child.timeout = 600
        listening(guest, 17051)
        guest.command(". /usr/local/pkg/nix9/system")
        check_profile(guest, "alice", "two")
        check_profile(guest, "bob", "one")
        login(guest, "alice", "roots=`{nix-store --roots-dir}; nix-profile $roots/environment rollback")
        check_profile(guest, "alice", "one")
        guest.command("nix-store --gc")
        check_profile(guest, "alice", "one")
        check_profile(guest, "bob", "one")
        guest.command("nix9-rebuild switch /tmp/disabled.nix")
        check_profile(guest, "bob", "one")
    print("PASS: system rollback preserves both user profiles and their generations across GC", flush=True)

    with start() as guest:
        guest.child.timeout = 600
        guest.command(". /usr/local/pkg/nix9/system")
        guest.command("if(netstat -n | grep -s 'Listen *1705[12] ') exit 'store is still listening'; status=''")
        login(guest, "alice", "echo $NIX_REMOTE", "local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log")
        guest.command("test -r /usr/local/nix/state/gcroots/per-user/alice/environment")
        guest.command("test -r /usr/local/nix/state/gcroots/per-user/bob/environment")
    print("PASS: disabling removes the listener and client default at reboot, retaining user roots", flush=True)

Path(output).mkdir(parents=True, exist_ok=True)
Path(output, "results.json").write_text(json.dumps({"status": "passed", "checks": [
    "private-runtime-keys", "manual-port-collision", "managed-startup", "ordinary-login",
    "owner-local-store", "protected-store", "native-client-identity", "booted-client-defaults", "policy-and-port-reboot", "server-owned-nix-settings",
    "policy-rollback", "retained-user-profiles", "user-profile-rollback", "gc", "disable",
]}, indent=2) + "\n")
