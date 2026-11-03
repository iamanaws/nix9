"""One CPU, authenticated users, shared packages and a separate build identity."""

import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time

from guest import files_guest
from shared_profiles import check_profiles


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def output_path(result):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
    if len(paths) != 1:
        raise RuntimeError(f"expected one output path: {result}")
    return paths[0]


qemu, image, archive, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    disk = work / "shared.qcow2"
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2", "-F", "qcow2",
                    "-b", str(Path(image).resolve()), str(disk)], check=True)
    fixtures = {"bootstrap.tar": archive, "shared-store.nix": Path(__file__).with_name("shared-store.nix")}
    fixtures["shared-detached.c"] = Path(__file__).with_name("shared-detached.c")
    fixtures["remote-delay.c"] = Path(__file__).with_name("remote-delay.c")
    client = work / "shared-client.rc"
    client.write_text("flag e +\n. /usr/local/pkg/nix9/activate\n"
                      "mkdir -p $home/tmp\nTMPDIR=$home/tmp\n"
                      "NIX_REMOTE='daemon?key-pattern=dom=nix9.shared user='^$user\n"
                      "machineStore='local?store=/usr/local/nix/store&state=/usr/local/nix/state'\n"
                      "fn machine { nix-store --store $machineStore $* }\n"
                      "fn package { nix-build $nix9/packages --no-out-link -A $* }\n"
                      "fn shared { nix-build /usr/shared-store.nix --no-out-link -A $* }\n"
                      "fn environment { nix-build $nix9/packages/examples/workstation/project/environment.nix --no-out-link }\n"
                      "$*\n")
    fixtures[client.name] = client
    job = work / "shared-job.rc"
    job.write_text("name=$1\nshift\necho $pid > $home/$name.pid\n"
                   "exec nix-build /usr/shared-store.nix --no-out-link $*\n")
    fixtures[job.name] = job
    for user in ("nixhost", "alice", "bob", "carol"):
        key = secrets.token_bytes(16)
        role = "server" if user == "nixhost" else "client"
        owner = "glenda" if user == "nixhost" else user
        for suffix, data in (("aes", key), ("keys", f"key proto=dp9ik dom=nix9.shared user={user} role={role} "
                              f"owner={owner} !hex={key.hex()} !password=______\n".encode())):
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
        guest.child.timeout = 600
        guest.command("cd / && tar xf /tmp/bootstrap.tar && rm /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("ip/ipconfig -P loopback /dev/null 127.1")
        guest.command("chmod 777 /tmp")
        guest.command("cp /tmp/shared-store.nix /usr/shared-store.nix && chmod 444 /usr/shared-store.nix")
        guest.command("cp /tmp/shared-detached.c /usr/shared-detached.c && chmod 444 /usr/shared-detached.c")
        guest.command("cp /tmp/remote-delay.c /usr/remote-delay.c && chmod 444 /usr/remote-delay.c")
        guest.command("cp /tmp/shared-client.rc /usr/shared-client.rc && chmod 444 /usr/shared-client.rc")
        guest.command("cp /tmp/shared-job.rc /usr/shared-job.rc && chmod 444 /usr/shared-job.rc")
        for user in ("alice", "bob", "carol"):
            guest.command("echo 'newuser " + user + "' >> /srv/hjfs.cmd")
        guest.command("echo disallow >> /srv/hjfs.cmd")
        guest.command("nix-build '<nix9>' -A auth --out-link /usr/local/nix/state/gcroots/shared-auth")
        guest.command("authpkg=`{cat /usr/local/nix/state/gcroots/shared-auth}")
        guest.command("dd -if /tmp/nvram -of /dev/sdF0/nvram -bs 126 -count 1")
        guest.command("rm /tmp/nvram")
        guest.command("echo 'authdom=nix9.shared auth=127.0.0.1' >> /lib/ndb/local; echo refresh > /net/cs")
        guest.command("$authpkg/bin/auth/keyfs -s shared-keys -m /mnt/keys /adm/shared.keys </dev/null")
        for user in ("nixhost", "alice", "bob", "carol"):
            guest.command(f"mkdir /mnt/keys/{user}; cp /tmp/{user}.aes /mnt/keys/{user}/aeskey")
            guest.command(f"cat /tmp/{user}.keys > /mnt/factotum/ctl; rm /tmp/{user}.keys /tmp/{user}.aes")
        guest.command("test -f /adm/shared.keys && chmod 600 /adm/shared.keys")
        guest.command("mkdir -p /adm/shared-auth /adm/shared-empty")
        guest.command("echo '#!/bin/rc' > /adm/shared-auth/tcp567")
        guest.command("echo 'mount /srv/shared-keys /mnt/keys || exit' >> /adm/shared-auth/tcp567")
        guest.command("echo 'exec '^$authpkg^'/bin/auth/authsrv -N $3' >> /adm/shared-auth/tcp567")
        guest.command("chmod 755 /adm/shared-auth/tcp567")
        guest.command("aux/listen -q -t /adm/shared-auth -d /adm/shared-empty tcp")
        guest.command("echo alice bob > /adm/shared-allowed; chmod 644 /adm/shared-allowed")
        guest.command("$nix9/bin/nix-store-service -k 'dom=nix9.shared user=nixhost' -u /adm/shared-allowed "
                      "-w $nix9/bin/nix-daemon-worker </dev/null >/tmp/shared-service.log >[2=1] &")
        guest.command("sleep 1; cat /tmp/shared-service.log; netstat -n")
        guest.command("netstat -n | grep 'Listen *17051 '")
        guest.command("fn as { auth/as $1 /bin/rc /usr/shared-client.rc /bin/rc -c $2 }")

        def user_command(user, command):
            line = "as " + user + " " + quote(command)
            if len(line) > 220:
                # The serial console can drop a byte at its line-buffer boundary.
                guest.command("echo -n > /tmp/shared-command; chmod 644 /tmp/shared-command")
                for offset in range(0, len(command), 100):
                    guest.command("echo -n " + quote(command[offset:offset + 100]) + " >> /tmp/shared-command")
                line = "as " + user + " '. /tmp/shared-command'"
            return guest.command(line)

        def rejected(user, command, reason):
            result = user_command(user, "rc -c " + quote(command) + "; echo SHARED-ERROR:$status")
            if not re.search(r"(?m)^SHARED-ERROR:.+", result) or reason.lower() not in result.lower():
                raise RuntimeError(f"unexpected shared-store rejection: {result}")

        def until(command, description, timeout=30):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                result = guest.command("if(" + command + ") echo SHARED-READY; status=''")
                if re.search(r"(?m)^SHARED-READY$", result):
                    return
                time.sleep(0.1)
            raise RuntimeError("timed out waiting for " + description)

        def clean_builds():
            until("test `{ls /usr/local/nix/state/builds | wc -l} -eq 0", "build directory cleanup")
            guest.command("if(ls /srv | grep -s 'nix9-build-') exit 'build filesystem was retained'; status=''")
            until("test `{ls /usr/local/nix/state/db/clients | wc -l} -eq 0", "daemon worker exit")
            until("test `{ps | awk '$1 == \"alice\" || $1 == \"bob\"' | wc -l} -eq 0", "user client/helper exit")
            until("test `{ps | grep ' (nix-daemon-worker|nix-ramfs)$' | wc -l} -eq 0", "server worker/helper exit")
            until("test `{ps | grep ' nix-store-service$' | wc -l} -eq 1", "connection helper exit")

        def start_job(user, name, args):
            guest.command("@{ auth/as " + user + " /bin/rc /usr/shared-client.rc /bin/rc /usr/shared-job.rc "
                          + name + " " + args + " >/tmp/" + name + ".log >[2=1]; "
                          "echo $status >/tmp/" + name + ".status } &")

        try:
            user_command("alice", "for(i in " + " ".join(str(i) for i in range(20)) + ") { "
                         "r=`{nix-store --roots-dir}; "
                         "~ $r /usr/local/nix/state/gcroots/per-user/alice || exit 'wrong roots'; "
                         "nix-store --roots-dir || exit; }")
            first = user_command("alice", "package rc --max-jobs 0")
            compiler = output_path(first)
            if "copying path" not in first or "building '" in first:
                raise RuntimeError("Alice did not use the signed cache: " + first)
            second = user_command("bob", "package rc --max-jobs 0")
            if output_path(second) != compiler or "copying path" in second or "building '" in second:
                raise RuntimeError("Bob did not reuse the shared compiler: " + second)
            for user in ("alice", "bob"):
                user_command(user, "test ! -w /usr/local/nix/store && test ! -w /usr/local/nix/state/db/db.sqlite")
                user_command(user, "test ! -d $home/nix")
                rejected(user, "machine --check-validity " + compiler, "permission denied")
            query = "nix-store -q --hash " + compiler
            rejected("carol", query, "cannot open connection")
            guest.command("chmod 666 /adm/shared-allowed")
            rejected("alice", query, "cannot open connection")
            guest.command("chmod 644 /adm/shared-allowed")
            guest.command("echo bob > /adm/shared-allowed")
            rejected("alice", "user=bob; " + query, "cannot open connection")
            guest.command("echo alice bob > /adm/shared-allowed")
            print("PASS: authenticated users reuse one signed package without private stores or database access", flush=True)

            for user, attribute in (("alice", "one"), ("bob", "two")):
                built = output_path(user_command(user, "shared " + attribute))
                user_command(user, f"echo `{{cat {built}/identity}}")
                guest.command(f"echo `{{cat {built}/identity}}", "none")
                guest.command(f"cat {built}/private/result", "private-output")
                guest.command(f"nix-store --verify-path {built}")
            large = output_path(user_command("alice", "shared largeInput"))
            guest.command("test `{wc -c < " + large + "} -eq 65536")
            detached = output_path(user_command("alice", "shared detached"))
            guest.command("writer=`{cat " + detached + "/pid}; sleep 1; test ! -d /proc/$writer")
            guest.command("cat " + detached + "/live", "x")
            queued = user_command("bob", "shared queued --max-jobs 2")
            if len(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", queued)) != 2:
                raise RuntimeError("queued builds did not both finish: " + queued)
            environment = output_path(user_command("alice", "environment"))
            user_command("alice", f". {environment}/activate && hello")
            reused = user_command("bob", "environment")
            if output_path(reused) != environment or "building '" in reused:
                raise RuntimeError("Bob rebuilt the shared C environment: " + reused)
            rejected("alice", "shared failure", "intentional shared build failure")
            for iteration in range(5):
                rejected("bob", "shared timeout --timeout 1", "timed out")
                clean_builds()
                recovered = output_path(user_command("alice", "shared recovery --argstr recoveryName timeout-recovery-" + str(iteration)))
                guest.command("nix-store --verify-path " + recovered)
            print("PASS: repeated timeouts return valid errors and another user can build afterward", flush=True)

            interruptions = [("cancel", "interrupt")] + [("kill-" + str(i), "kill") for i in range(3)]
            for name, note in interruptions:
                start_job("alice", name, "-A timeout")
                until("grep -s '^SHARED-WAITING$' /tmp/" + name + ".log", name + " build start")
                start_job("bob", name + "-queued", "-A queued --max-jobs 2 --argstr recoveryName " + name)
                until("grep -s 'waiting for a free build user ID' /tmp/" + name + "-queued.log", "second user's queued build")
                user_command("alice", "job=`{cat $home/" + name + ".pid}; echo " + note + " > /proc/$job/note")
                until("test -f /tmp/" + name + ".status", name + " client exit", timeout=10)
                guest.command("test `{wc -c </tmp/" + name + ".status} -gt 1")
                until("test -f /tmp/" + name + "-queued.status", "queued builds after " + name, timeout=20)
                log = guest.command("cat /tmp/" + name + "-queued.log")
                if len(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", log)) != 2:
                    raise RuntimeError("queued builds failed after " + name + ": " + log)
                guest.command("test `{wc -c </tmp/" + name + "-queued.status} -eq 1")
                clean_builds()
                output_path(user_command("alice", "shared recovery --argstr recoveryName " + name + "-reconnected"))
            print("PASS: repeated client death cleans up processes and releases queued builds without restarting the service", flush=True)
            guest.command(f"nix-store --verify-path {compiler}")
            clean_builds()
            print("PASS: separate build identity, protected shared packages and credentials, private output import and cleanup", flush=True)
            check_profiles(guest, user_command, rejected, clean_builds)
        except Exception:
            guest.command("ps; cat /tmp/shared-service.log; echo")
            raise
Path(output).mkdir(parents=True, exist_ok=True)
Path(output, "results.json").write_text(json.dumps({"status": "passed", "users": ["alice", "bob"], "checks": [
    "native-authentication", "signed-cache", "shared-package-reuse", "store-permissions", "denied-user",
    "authenticated-identity-policy", "separate-builder-identity", "protected-inputs", "protected-credentials",
    "private-output-import", "native-c-build", "shared-environment-reuse", "failed-build-cleanup",
    "anonymous-process-permissions", "detached-writer-revocation",
    "queued-builds", "repeated-timeout-recovery", "cancellation-recovery", "disconnected-client-recovery",
    "repeated-client-death", "client-and-server-process-cleanup",
    "user-roots", "independent-profiles", "profile-rollback", "concurrent-profile-updates", "shared-root-gc",
    "root-access-policy", "consecutive-client-connections",
]}, indent=2) + "\n")
