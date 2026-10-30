"""Prepare and select an installation through native authenticated CPU sessions."""

from contextlib import ExitStack, contextmanager, nullcontext
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

from artifacts import ArtifactServer
from guest import boot


ROOTS = "/usr/local/nix/state/gcroots"
CPU_PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def store_path(guest, root):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat " + root))
    if len(paths) != 1:
        raise RuntimeError(f"missing store path: {root}")
    return paths[0]


def selected(guest, name):
    return store_path(guest, ROOTS + "/machines/" + name + "/system")


def rejected(guest, command, reason=None):
    result = guest.command("rc -c " + quote(command) + "; echo DEPLOY-ERROR:$status")
    if (not re.search(r"(?m)^DEPLOY-ERROR:.+", result) or "syntax error" in result
            or (reason and reason not in result)):
        raise RuntimeError(f"operation was not rejected: {command}: {result}")
    return result


def stop(guest):
    guest.child.sendline("fshalt")
    guest.child.expect("done halting")
    guest.crash()


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_DEPLOYMENT_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    for name in ("deployment.nix", "deployment-truncate.rc", "deployment-store.rc",
                 "deployment-stop.rc", "deployment-target.rc"):
        shutil.copyfile(Path(__file__).with_name(name), work / name)

    keys = {name: secrets.token_bytes(16) for name in ("files", "cpu", "glenda")}
    for name, roles in {"files": ["server"], "cpu": ["server", "speakfor"], "glenda": ["client"]}.items():
        commands = "".join(f"key proto=dp9ik dom=nix9.share user={name} role={role} "
                           f"!hex={keys[name].hex()} !password=______\n" for role in roles)
        for suffix, data in (("keys", commands.encode()), ("aes", keys[name])):
            file = work / f"{name}.{suffix}"
            file.write_bytes(data)
            file.chmod(0o600)
    for name in ("files", "cpu", "terminal"):
        domain = b"nix9.share" if name == "files" else b"bootstrap.invalid"
        fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
                  domain.ljust(48, b"\0"), secrets.token_bytes(16))
        nvram = work / (name + ".nvram")
        nvram.write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
        nvram.chmod(0o600)

    server = stack.enter_context(ArtifactServer(work, work / "bundle.export"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join)
    stack.callback(server.shutdown)
    base = f"http://10.0.2.2:{server.server_port}"

    def download(guest, name, destination=None, private=False):
        destination = destination or "/tmp/" + name
        if private:
            guest.command(f"echo -n > {destination}; chmod 600 {destination}")
        guest.command(f"hget -o {destination} {base}/{name}")

    peers = []
    reservations = {}
    for address, port in (("10.0.2.100", 567), ("10.0.2.100", 17020), ("10.0.2.101", 17019)):
        reservation = stack.enter_context(socket.socket())
        reservation.bind(("127.0.0.1", 0))
        host_port = reservation.getsockname()[1]
        peers.append((address, port, host_port))
        reservations[host_port] = reservation

    disks, systems, bundles = {}, {}, {}
    # Install the common bootstrap once, then give each machine an independent
    # writable disk and database. This base has no saved machine identity.
    foundation = work / "bootstrap.qcow2"
    if foundation.exists():
        raise RuntimeError(f"refusing to overwrite an existing VM: {foundation}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(foundation)], check=True)
    with boot(qemu, foundation, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix-build '<nix9>' -A auth -A rcpu -A ndb -A listen --out-link " + ROOTS + "/deployment-tools")
    for name in ("files", "cpu", "terminal"):
        disk = work / f"{name}.qcow2"
        if disk.exists():
            raise RuntimeError(f"refusing to overwrite an existing VM: {disk}")
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                        "-F", "qcow2", "-b", str(foundation.resolve()), str(disk)], check=True)
        disks[name] = disk
        with boot(qemu, disk, snapshot=False) as guest:
            guest.child.timeout = 900
            guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init " + name)
            download(guest, "deployment.nix")
            download(guest, name + ".nvram", "/tmp/boot.nvram", private=True)
            guest.command("dd -if /tmp/boot.nvram -of /dev/sdF0/nvram -bs 126 -count 1")
            if name == "files":
                guest.command("rm -f /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                for identity in keys:
                    download(guest, identity + ".aes", private=True)
                    guest.command(f"mkdir /mnt/keys/{identity}")
                    guest.command(f"cp /tmp/{identity}.aes /mnt/keys/{identity}/aeskey")
                download(guest, "files.keys", "/adm/files.keys", private=True)
                download(guest, "glenda.keys", "/adm/scheduler.keys", private=True)
                for fixture in ("deployment-truncate.rc", "deployment-store.rc",
                                "deployment-stop.rc", "deployment-target.rc"):
                    download(guest, fixture)
                guest.command("chmod 755 /tmp/deployment-store.rc")
            elif name == "cpu":
                download(guest, "cpu.keys", "/adm/cpu.keys", private=True)
            else:
                download(guest, "glenda.keys", "/adm/terminal.keys", private=True)
                guest.command("echo 'cat /adm/terminal.keys > /mnt/factotum/ctl' > /rc/bin/termrc.local")
            if name != "terminal":
                guest.command(f"mkdir -p /cfg/{name}/service")
            guest.command("nix-build /tmp/deployment.nix -A one.systems." + name + " --out-link " + ROOTS + "/initial")
            systems[name] = store_path(guest, ROOTS + "/initial")
            guest.command("nix9-rebuild select " + systems[name])
            if name == "files":
                for revision in ("one", "two", "wrong", "unreachable"):
                    guest.command(f"nix-build /tmp/deployment.nix -A {revision}.build --out-link {ROOTS}/{revision}")
                    bundles[revision] = store_path(guest, ROOTS + "/" + revision)
                intended = {machine: store_path(guest, bundles["two"] + "/systems/" + machine)
                            for machine in ("files", "cpu", "terminal")}
                guest.command("echo shared-data > /usr/glenda/projects/data")
            else:
                guest.command("rm /tmp/deployment.nix")
                guest.command("echo 'substituters =' > $nix9/nix.conf; echo 'max-jobs = 0' >> $nix9/nix.conf")
            if name != "terminal":
                guest.command("9fs 9fat")
                guest.command("echo 'service=cpu' >> /n/9fat/plan9.ini; echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    @contextmanager
    def start(name):
        address = {"files": "10.0.2.100", "cpu": "10.0.2.101"}.get(name)
        forwards = [(host, port) for peer, port, host in peers if peer == address]
        for host, _ in forwards:
            reservations[host].close()
        with boot(qemu, disks[name], snapshot=False, configure_network=False,
                  guest_forwards=peers, forward_ports=forwards, cpu=name != "terminal",
                  prompt=CPU_PROMPT if name != "terminal" else r"(?m)^(?:term)?% ") as guest:
            guest.child.timeout = 600
            guest.command(". /usr/local/pkg/nix9/activate")
            guest.command("webfs")
            yield guest

    provider = stack.enter_context(start("files"))
    cpu = stack.enter_context(start("cpu"))
    terminal = stack.enter_context(start("terminal"))
    two = bundles["two"]
    before = {"files": selected(provider, "files"), "cpu": selected(cpu, "cpu")}
    status = provider.command(f"rc -ex $nix9/bin/nix9-deploy status {two} files cpu")
    for name in before:
        for field, path in (("intended", intended[name]), ("selected", before[name]), ("booted", before[name])):
            if f"{name} {field} {path}\n" not in status:
                raise RuntimeError(f"incorrect deployment status: {status}")
    rejected(provider, f"nix9-deploy prepare {bundles['wrong']} cpu", "identity differs")
    rejected(provider, f"nix9-deploy status {bundles['unreachable']} cpu files", "could not be queried")
    rejected(provider, f"nix9-deploy prepare {two} terminal", "needs local deployment")
    local_only = rejected(provider, f"nix9-deploy status {two} terminal files", "could not be queried")
    if f"files selected {before['files']}\n" not in local_only:
        raise RuntimeError("a local-only machine prevented querying the remaining machines")
    print("PASS: live intended/selected/booted status, identity checks and unavailable nodes", flush=True)

    provider.command(f"nix9-deploy prepare {two} files")
    rejected(provider, f"nix9-deploy select {two} files", "has not prepared")
    if selected(provider, "files") != before["files"]:
        raise RuntimeError("scheduler changed before its job target was prepared")
    rejected(provider, f"rc /tmp/deployment-truncate.rc {two} cpu", "closure import failed")
    cpu.command("test ! -e " + ROOTS + "/deployments/lab/cpu")
    if selected(cpu, "cpu") != before["cpu"]:
        raise RuntimeError("truncated transfer changed the target generation")
    retry = provider.command(f"nix9-deploy prepare {two} cpu")
    if re.search(r"(?m)^Exporting ", retry):
        raise RuntimeError("retry exported objects that the interrupted import had registered")
    for guest, name in ((provider, "files"), (cpu, "cpu")):
        if selected(guest, name) != before[name]:
            raise RuntimeError("preparation changed a selection")
        guest.command("cat " + ROOTS + "/deployments/lab/" + name, intended[name])
    cpu.command("nix-store --gc; nix-store --verify-path " + intended["cpu"])
    print("PASS: interrupted import preserves selections; retry reuses objects and prepared roots survive GC", flush=True)

    # Fail a later target's preflight. No earlier requested selection may change.
    cpu.command("cp /rc/bin/cpurc.local /tmp/saved-cpurc; echo '# manual edit' >> /rc/bin/cpurc.local")
    rejected(provider, f"nix9-deploy select {two} files cpu", "startup hook was edited")
    if selected(provider, "files") != before["files"]:
        raise RuntimeError("selection started before all machine checks passed")
    cpu.command("cp /tmp/saved-cpurc /rc/bin/cpurc.local")
    rejected(provider, f"rc /tmp/deployment-stop.rc {two} files cpu", "selection stopped at cpu")
    if selected(provider, "files") != intended["files"] or selected(cpu, "cpu") != before["cpu"]:
        raise RuntimeError("interrupted selection did not preserve the completed machine")
    mixed = provider.command(f"nix9-deploy status {two} files cpu")
    if f"files selected {intended['files']}\n" not in mixed or f"cpu selected {before['cpu']}\n" not in mixed:
        raise RuntimeError("status did not report the interrupted deployment accurately")
    provider.command(f"nix9-deploy select {two} files cpu")
    histories = {name: guest.command("nix9-rebuild list") for guest, name in ((provider, "files"), (cpu, "cpu"))}
    provider.command(f"nix9-deploy select {two} files cpu")
    for guest, name in ((provider, "files"), (cpu, "cpu")):
        if selected(guest, name) != intended[name] or guest.command("nix9-rebuild list") != histories[name]:
            raise RuntimeError("repeated deployment changed generation history")
    status = provider.command(f"nix9-deploy status {two} files cpu")
    if not all(f"{name} reboot required\n" in status for name in ("files", "cpu")):
        raise RuntimeError("selection was reported as already booted")
    print("PASS: all-machine preflight, job target readiness, selection, generation reuse and pending reboot", flush=True)

    provider.command("nix-store --export `{nix-store -qR " + two + "} > /tmp/bundle.export")
    provider.command("size=`{ls -l /tmp/bundle.export | awk '{print $6}'}")
    provider.command("hget -r 'Content-Length: '^$size -P " + base + "/bundle.export < /tmp/bundle.export")
    if not server.received.is_set():
        raise RuntimeError("installation bundle was not uploaded")
    download(terminal, "bundle.export")
    terminal.command("nix-store --import < /tmp/bundle.export > /dev/null")
    terminal.command(f"nix9-deploy prepare {two} terminal; nix9-deploy select {two} terminal")
    if selected(terminal, "terminal") != intended["terminal"]:
        raise RuntimeError("local terminal deployment selected the wrong system")
    print("PASS: terminal deploys locally from an imported bundle without configuration or builds", flush=True)

    stop(cpu)
    cpu = stack.enter_context(start("cpu"))
    provider.command(f"nix9-deploy status {two} cpu", "cpu reboot no")
    cpu.command(". /usr/local/pkg/nix9/system; cat /cfg/nix9/files/deployment", "two")
    cpu.command("cat /n/projects/data", "shared-data")
    cpu.command("nix9-rebuild rollback")
    provider.command(f"nix9-deploy status {two} cpu", "cpu reboot required")
    stop(cpu)
    cpu = stack.enter_context(start("cpu"))
    provider.command(f"nix9-deploy status {two} cpu", "cpu reboot no")
    if selected(cpu, "cpu") != before["cpu"]:
        raise RuntimeError("rollback did not restore the original generation")
    cpu.command(". /usr/local/pkg/nix9/system; cat /cfg/nix9/files/deployment", "one")
    cpu.command("cat /n/projects/data", "shared-data")
    print("PASS: explicit reboot and native rollback preserve independent generations and shared data", flush=True)

    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "machines": 3, "cpuReboots": 2, "bundles": bundles,
        "checks": ["authenticated-rcpu", "live-status", "wrong-identity", "unavailable-nodes",
                   "local-terminal", "scheduler-target-readiness", "truncated-transfer",
                   "retry-reuses-objects", "prepare-without-selection", "prepared-gc-roots",
                   "all-machine-preflight", "interrupted-selection-recovery", "selection", "generation-reuse", "pending-reboot",
                   "no-target-configuration-or-build", "explicit-reboot", "rollback", "shared-data"],
    }, indent=2) + "\n")
