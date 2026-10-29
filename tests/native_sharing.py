"""Use a shared project across distinct file/auth, CPU and terminal machines."""

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


CPU_PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"
INVALID = {
    "invalidExportPath": "path", "invalidExportUsers": "allowedUsers",
    "invalidExportUser": "allowedUsers", "invalidExportPort": "port",
    "duplicateExportPort": "distinct TCP ports", "reservedExportPort": "CPU ports",
    "conflictingExportPort": "must not share a TCP port", "secretExportPattern": "keyPattern",
    "storedExportKey": "keyFile", "invalidMountAddress": "address",
    "invalidMountPoint": "mountPoint", "storedMountPoint": "mountPoint",
    "protectedMountPoint": "local Nix runtime",
    "overlappingMounts": "must not overlap", "invalidMountTimeout": "timeout",
    "secretMountPattern": "keyPattern",
}


def selected(guest, identity):
    output = guest.command(f"cat /usr/local/nix/state/gcroots/machines/{identity}/system")
    values = re.findall(r"(?m)^/usr/local/nix/store/\S+$", output)
    if len(values) != 1:
        raise RuntimeError(f"missing system selection: {identity}: {output}")
    return values[0]


def rejected(guest, command, reason=None):
    result = guest.command("rc -c " + quote(command) + "; echo SHARING-ERROR:$status")
    if (not re.search(r"(?m)^SHARING-ERROR:.+", result)
            or "syntax error" in result or (reason and reason not in result)):
        raise RuntimeError(f"operation was not rejected: {command}: {result}")
    return result


def listening(guest, ports, present=True):
    deadline = time.monotonic() + 20
    while True:
        table = guest.command("netstat -n")
        active = [bool(re.search(r"(?m)^tcp\s+\d+\s+\S+\s+Listen\s+" + str(port) + r"\s", table))
                  for port in ports]
        if all(value == present for value in active):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"unexpected listening ports: {ports}: {table}")
        time.sleep(0.1)


def download(guest, base, name, destination=None, private=False):
    destination = destination or "/tmp/" + name
    if private:
        guest.command(f"echo -n > {destination}; chmod 600 {destination}")
    guest.command(f"hget -o {destination} {base}/{name}")


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def remote(terminal, command, expected=None):
    return terminal.command("rcpu -h cpu -c " + quote(command), expected)


def stop(guest):
    guest.child.sendline("fshalt")
    guest.child.expect("done halting")
    guest.crash()


def store_path(guest, root):
    output = guest.command("cat " + root)
    return re.findall(r"(?m)^/usr/local/nix/store/\S+$", output)[0]


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_SHARING_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("sharing.nix"), work / "sharing.nix")
    shutil.copyfile(Path(__file__).with_name("machine-newns.c"), work / "machine-newns.c")
    shutil.copyfile(Path(__file__).with_name("sharing-failed-refresh.rc"), work / "sharing-failed-refresh.rc")
    shutil.copytree(Path(__file__).with_name("sharing-project"), work / "project")

    # Credentials are generated outside derivations and outputs. CPU delegation
    # lets authenticated user sessions open the file share using the CPU's key.
    keys = {name: secrets.token_bytes(16) for name in ("files", "cpu", "glenda")}
    for name, roles in {"files": ["server"], "cpu": ["server", "speakfor"], "glenda": ["client"]}.items():
        commands = "".join(f"key proto=dp9ik dom=nix9.share user={name} role={role} "
                           f"!hex={keys[name].hex()} !password=______\n" for role in roles)
        if name == "cpu":
            commands = "# CPU access and delegation keys\n\n" + commands
        for suffix, data in (("keys", commands.encode()), ("aes", keys[name])):
            file = work / f"{name}.{suffix}"
            file.write_bytes(data)
            file.chmod(0o600)
    bad = work / "bad.keys"
    bad.write_text("key proto=dp9ik dom=nix9.share user=glenda role=client "
                   f"!hex={secrets.token_hex(16)} !password=______\n")
    bad.chmod(0o600)
    for name in ("files", "cpu", "terminal"):
        # Keep the native filesystem owner, with separate boot credentials.
        # Session/server keys for nix9.share are loaded explicitly below.
        domain = b"nix9.share" if name == "files" else b"bootstrap.invalid"
        fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
                  domain.ljust(48, b"\0"), secrets.token_bytes(16))
        nvram = work / (name + ".nvram")
        nvram.write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
        nvram.chmod(0o600)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    http = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join)
    stack.callback(http.shutdown)
    base = f"http://10.0.2.2:{http.server_port}"

    peers = []
    reservations = {}
    for address, port in (("10.0.2.100", 567), ("10.0.2.100", 17020),
                          ("10.0.2.100", 17021), ("10.0.2.100", 17022),
                          ("10.0.2.101", 17019)):
        reservation = stack.enter_context(socket.socket())
        reservation.bind(("127.0.0.1", 0))
        host_port = reservation.getsockname()[1]
        peers.append((address, port, host_port))
        reservations[host_port] = reservation

    disks = {}
    systems = {}
    for name in ("files", "cpu", "terminal"):
        disk = work / f"{name}.qcow2"
        if disk.exists():
            raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                        "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
        disks[name] = disk
        with boot(qemu, disk, snapshot=False) as guest:
            guest.child.timeout = 900
            guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
            guest.command(". /usr/local/pkg/nix9/activate")
            guest.command("nix9-rebuild init " + name)
            download(guest, base, "sharing.nix")
            for configuration in ("files", "readOnly", "disabled", "cpu", "terminal", "moved",
                                  "optional", "unavailable", "empty"):
                guest.command(f"echo '(import ./sharing.nix {{}}).{configuration}' > /tmp/{configuration}.nix")
            download(guest, base, name + ".nvram", "/tmp/boot.nvram", private=True)
            guest.command("dd -if /tmp/boot.nvram -of /dev/sdF0/nvram -bs 126 -count 1")
            if name == "files":
                guest.command("rm -f /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                for identity in keys:
                    download(guest, base, identity + ".aes", private=True)
                    guest.command(f"mkdir /mnt/keys/{identity}")
                    guest.command(f"cp /tmp/{identity}.aes /mnt/keys/{identity}/aeskey")
                download(guest, base, "files.keys", "/adm/files.keys", private=True)
                guest.command("mkdir -p /usr/glenda/projects")
                for file in ("default.nix", "hello.c", "mkfile"):
                    download(guest, base, "project/" + file, "/usr/glenda/projects/" + file)
                guest.command("echo private > /usr/glenda/projects/locked; chmod 000 /usr/glenda/projects/locked")
            elif name == "cpu":
                download(guest, base, "cpu.keys", "/adm/cpu.keys", private=True)
            else:
                download(guest, base, "glenda.keys", "/adm/terminal.keys", private=True)
                download(guest, base, "bad.keys", private=True)
                guest.command("cat /adm/terminal.keys > /mnt/factotum/ctl")
                guest.command("echo 'cat /adm/terminal.keys > /mnt/factotum/ctl' > /rc/bin/termrc.local")
                download(guest, base, "machine-newns.c")
                download(guest, base, "sharing-failed-refresh.rc")
                guest.command("cd /tmp && 6c machine-newns.c && 6l -o newns machine-newns.6")
            if name != "terminal":
                guest.command(f"mkdir -p /cfg/{name}/service")
            guest.command(f"nix9-rebuild switch /tmp/{name}.nix")
            systems[name] = selected(guest, name)
            if name == "files":
                for invalid, reason in INVALID.items():
                    rejected(guest, f"nix-instantiate --eval --strict --expr '(import /tmp/sharing.nix {{}}).{invalid}.drvPath'", reason)
                guest.command("chmod 644 /adm/files.keys")
                rejected(guest, "nix9-rebuild switch /tmp/readOnly.nix", "unsafe permissions")
                guest.command("chmod 600 /adm/files.keys")
                guest.command("mv /usr/glenda/projects /usr/glenda/saved-projects")
                rejected(guest, "nix9-rebuild switch /tmp/readOnly.nix", "export directory is unavailable")
                guest.command("mv /usr/glenda/saved-projects /usr/glenda/projects")
                if selected(guest, name) != systems[name]:
                    raise RuntimeError("rejected export configuration changed the selection")
            if name != "terminal":
                guest.command("9fs 9fat")
                guest.command("echo 'service=cpu' >> /n/9fat/plan9.ini")
                guest.command("echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")
    print("PASS: three independent stores, typed configurations and runtime preflight", flush=True)

    @contextmanager
    def start(name):
        address = {"files": "10.0.2.100", "cpu": "10.0.2.101"}.get(name)
        forwards = [(host, port) for peer, port, host in peers if peer == address]
        for host, _ in forwards:
            reservations[host].close()
        with boot(qemu, disks[name], snapshot=False, configure_network=False,
                  guest_forwards=peers, cpu=name != "terminal",
                  prompt=CPU_PROMPT if name != "terminal" else r"(?m)^(?:term)?% ",
                  forward_ports=forwards) as guest:
            guest.child.timeout = 300
            guest.command(". /usr/local/pkg/nix9/activate")
            root = selected(guest, name)
            guest.command(f"cat /usr/local/nix/state/gcroots/machines/{name}/system-boot", root)
            if name != "terminal":
                guest.command("test -e '#s/nix9-access-" + name + "'")
            yield guest

    provider = stack.enter_context(start("files"))
    provider.child.timeout = 300
    listening(provider, (567, 17020, 17021, 17022))
    cpu = stack.enter_context(start("cpu"))
    cpu.child.timeout = 300
    listening(cpu, (17019,))
    terminal = stack.enter_context(start("terminal"))
    terminal.child.timeout = 300
    terminal.command(". /usr/local/pkg/nix9/system")
    terminal.command("ndb/query sys files ip", "10.0.2.100")
    terminal.command("cat /n/projects/hello.c", "void")
    terminal.command("echo terminal-edit > /n/projects/terminal-edit")
    provider.command("cat /usr/glenda/projects/terminal-edit", "terminal-edit")
    terminal.command("sed 's/shared project original/edited on terminal, built on cpu/' "
                     "/n/projects/hello.c > /tmp/edited.c; cp /tmp/edited.c /n/projects/hello.c")
    rejected(terminal, "echo forbidden > /n/reference/readonly-test", "File system read only")
    rejected(terminal, "cat /n/projects/locked")
    provider.command("rm /usr/glenda/projects/locked")
    rejected(terminal, "alarm 3 tlsclient -a -k 'dom=nix9.share' tcp!files!17022 "
                      "/bin/mount -nc /fd/0 /n/rejected")
    terminal.command("echo 'delkey proto=dp9ik dom=nix9.share role=client' > /mnt/factotum/ctl")
    terminal.command("cat /tmp/bad.keys > /mnt/factotum/ctl")
    rejected(terminal, "@{ rfork n; bind /dev/null /dev/cons; bind /dev/null /dev/consctl; "
                      "alarm 3 tlsclient -a -k 'dom=nix9.share' tcp!files!17020 /bin/mount -nc /fd/0 /n/rejected }")
    terminal.command("echo 'delkey proto=dp9ik dom=nix9.share role=client' > /mnt/factotum/ctl")
    terminal.command("cat /adm/terminal.keys > /mnt/factotum/ctl")
    print("PASS: authenticated shared files, read-only exports, native permissions and rejected access", flush=True)

    remote(terminal, "nix-build /n/projects --out-link /usr/local/nix/state/gcroots/shared-project")
    built = store_path(cpu, "/usr/local/nix/state/gcroots/shared-project")
    cpu.command(built + "/bin/shared-project", "edited on terminal, built on cpu")
    terminal.command("test ! -e " + built)
    provider.command("test ! -e " + built)
    records = provider.command("cat /sys/log/auth")
    if not all(re.search(r"tr-ok glenda@" + identity + r".* -> glenda@files", records)
               for identity in ("cpu", "glenda")):
        raise RuntimeError("shared file access did not use direct and delegated authentication tickets")
    print("PASS: terminal edits shared sources; CPU uses delegated tickets and builds in its local store", flush=True)

    # Refresh changes only this namespace; a process already using it keeps its view.
    before = terminal.command("echo $nix9NamespaceMounts")
    terminal.command(". /usr/local/pkg/nix9/system")
    if terminal.command("echo $nix9NamespaceMounts") != before:
        raise RuntimeError("repeated activation replaced working connections")
    terminal.command("@{ rfork e; while(! test -e /tmp/check-old-session) sleep 0.05; "
                     "test -f /n/projects/hello.c && echo OLD-SESSION > /tmp/old-session-result } &")
    terminal.command("oldsession=$apid")
    terminal.command("nix9-rebuild switch /tmp/moved.nix")
    terminal.command(". /usr/local/pkg/nix9/system")
    terminal.command("test ! -f /n/projects/hello.c && test -f /n/work/hello.c")
    terminal.command("echo check > /tmp/check-old-session; wait $oldsession")
    terminal.command("cat /tmp/old-session-result", "OLD-SESSION")
    terminal.command("nix9-rebuild rollback; . /usr/local/pkg/nix9/system")
    terminal.command("test -f /n/projects/hello.c && test ! -f /n/work/hello.c")
    terminal.command("nix9-rebuild switch /tmp/optional.nix; . /usr/local/pkg/nix9/system")
    terminal.command("test -f /n/projects/hello.c && test ! -f /n/absent/hello.c")
    terminal.command("nix9-rebuild switch /tmp/unavailable.nix")
    result = rejected(terminal, "rc /tmp/sharing-failed-refresh.rc",
                      "required share is unavailable")
    if "OLD-MOUNT-PRESERVED\n" not in result:
        raise RuntimeError("a failed required connection removed the session's old mount")
    if "STAGED-MOUNTS-CLEANED\n" not in result:
        raise RuntimeError("a failed required connection leaked a staged mount")
    terminal.command("test -f /n/projects/hello.c")
    rejected(terminal, "/tmp/newns " + quote("exec rc -lc 'echo BAD-SESSION > /tmp/bad-session'"),
             "required share is unavailable")
    terminal.command("test ! -e /tmp/bad-session")
    terminal.command("nix9-rebuild switch /tmp/terminal.nix; . /usr/local/pkg/nix9/system")
    rejected(terminal, "@{ rfork n; bind /tmp /n/projects; . /usr/local/pkg/nix9/system }",
             "managed mount was changed")
    terminal.command("nix9-rebuild switch /tmp/empty.nix; . /usr/local/pkg/nix9/system")
    terminal.command("test ! -f /n/projects/hello.c && test ! -f /n/reference/hello.c")
    rejected(terminal, "@{ rfork n; bind /tmp /n/projects; nix9-rebuild switch /tmp/terminal.nix }",
             "a manual mount already owns")
    terminal.command("nix9-rebuild switch /tmp/terminal.nix; . /usr/local/pkg/nix9/system")
    print("PASS: mount reuse, private session views, retargeting, disable, rollback and missing providers", flush=True)

    provider.command("nix9-rebuild switch /tmp/readOnly.nix")
    remote(terminal, "echo boot-policy > /n/projects/boot-policy")
    # Close this provider context explicitly before starting its next boot.
    stop(provider)
    provider = stack.enter_context(start("files"))
    provider.child.timeout = 300
    listening(provider, (567, 17020, 17021, 17022))
    rejected(terminal, "rcpu -h cpu -c 'echo forbidden > /n/projects/after-boot'")
    provider.command("test ! -e /usr/glenda/projects/after-boot")
    provider.command("nix9-rebuild rollback")
    rejected(terminal, "rcpu -h cpu -c 'echo forbidden > /n/projects/before-rollback-boot'")
    stop(provider)
    provider = stack.enter_context(start("files"))
    provider.child.timeout = 300
    listening(provider, (567, 17020, 17021, 17022))
    remote(terminal, "cat /n/projects/terminal-edit", "terminal-edit")
    remote(terminal, "echo restored > /n/projects/restored")
    provider.command("cat /usr/glenda/projects/restored", "restored")
    provider.command("nix9-rebuild delete 2; nix9-rebuild switch /tmp/disabled.nix")
    print("PASS: export policy changes and rollback take effect at provider boot; project data survives", flush=True)

    stop(provider)
    provider = stack.enter_context(start("files"))
    provider.child.timeout = 300
    listening(provider, (567,))
    listening(provider, (17020, 17021, 17022), present=False)
    rejected(terminal, "rcpu -h cpu -c 'echo BAD-SESSION > /tmp/missing-share'", "required share is unavailable")
    cpu.command("test ! -e /tmp/missing-share")
    # Boot listeners independently of user-session shares, even without a provider.
    stop(cpu)
    cpu = stack.enter_context(start("cpu"))
    cpu.child.timeout = 300
    listening(cpu, (17019,))
    cpu.command(built + "/bin/shared-project", "edited on terminal, built on cpu")
    rejected(terminal, "rcpu -h cpu -c 'echo BAD-SESSION > /tmp/missing-share'", "required share is unavailable")
    cpu.command("test ! -e /tmp/missing-share")
    provider.command("nix9-rebuild rollback")
    stop(provider)
    provider = stack.enter_context(start("files"))
    provider.child.timeout = 300
    listening(provider, (567, 17020, 17021, 17022))
    remote(terminal, "cat /n/projects/restored", "restored")
    stop(terminal)
    terminal = stack.enter_context(start("terminal"))
    terminal.child.timeout = 300
    terminal.command(". /usr/local/pkg/nix9/system")
    terminal.command("cat /n/projects/terminal-edit", "terminal-edit")
    remote(terminal, built + "/bin/shared-project", "edited on terminal, built on cpu")
    print("PASS: disabled exports deny required sessions; CPU boot and all roles recover after reboot", flush=True)

    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "machines": 3, "configuredBoots": {"files": 5, "cpu": 2, "terminal": 2},
        "systems": systems, "remoteBuild": built, "rejectedConfigurations": list(INVALID),
        "checks": ["native-tls-9p", "separate-auth-and-cpu", "ndb-discovery", "delegated-tickets",
                   "terminal-edit-cpu-build", "independent-stores", "read-only-export", "native-permissions",
                   "wrong-credentials", "allowed-users", "runtime-preflight", "private-session-mounts",
                   "reuse", "retarget", "disable", "rollback", "required-and-optional-providers",
                   "manual-conflicts", "changed-mounts", "boot-only-export-policy", "persistent-project-data",
                   "boot-without-file-provider", "reboot-recovery"],
    }, indent=2) + "\n")
