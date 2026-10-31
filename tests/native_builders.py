"""Build from a terminal using authenticated CPU servers with independent stores."""

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
NAMES = ("auth", "build", "batch", "terminal")
PRIMARY = "cpu://build?key-pattern=dom%3Dnix9.builders"


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def paths(output):
    return re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", output)


def failed(guest, command, reason=None):
    output = guest.command("rc -c " + quote(command) + "; echo REMOTE-ERROR:$status")
    if not re.search(r"(?m)^REMOTE-ERROR:.+", output) or "syntax error" in output or (reason and reason not in output):
        raise RuntimeError(f"unexpected failure result: {command}: {output}")
    return output


def until(guest, command, seconds=30):
    deadline = time.monotonic() + seconds
    while True:
        output = guest.command(command + "; echo REMOTE-WAIT:$status")
        if re.search(r"(?m)^REMOTE-WAIT:$", output):
            return output
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for {command}: {output}")
        time.sleep(0.2)


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_BUILDER_TEST_STATE")
with ExitStack() as stack:
    work = Path(stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory()))
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    for name in ("builders.nix", "remote-project.nix"):
        shutil.copyfile(Path(__file__).with_name(name), work / name)
    shutil.copyfile(Path(__file__).with_name("remote-delay.c"), work / "delay.c")
    (work / "hello.c").write_text('#include <u.h>\n#include <libc.h>\n'
                                  'void main(void) { print("hello from a remote Nix builder\\n"); exits(nil); }\n')
    keys = {name: secrets.token_bytes(16) for name in ("build", "batch", "glenda")}
    for name, key in keys.items():
        role = "client" if name == "glenda" else "server"
        for suffix, data in (("keys", f"key proto=dp9ik dom=nix9.builders user={name} role={role} "
                              f"!hex={key.hex()} !password=______\n".encode()), ("aes", key)):
            file = work / (name + "." + suffix)
            file.write_bytes(data)
            file.chmod(0o600)
    (work / "bad.keys").write_text("key proto=dp9ik dom=nix9.builders user=glenda role=client "
                                    f"!hex={secrets.token_hex(16)} !password=______\n")
    (work / "bad.keys").chmod(0o600)
    for name in NAMES:
        fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
                  (b"nix9.builders" if name == "auth" else b"bootstrap.invalid").ljust(48, b"\0"), secrets.token_bytes(16))
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
    for address, port in (("10.0.2.100", 567), ("10.0.2.101", 17019), ("10.0.2.103", 17019)):
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
        guest.command("nix-build '<nix9>' -A auth -A rcpu -A ndb --out-link " + ROOTS + "/builder-tools")

    disks, systems = {}, {}
    for name in NAMES:
        disks[name] = work / (name + ".qcow2")
        disk(disks[name], foundation)
        with boot(qemu, disks[name], snapshot=False) as guest:
            guest.child.timeout = 900
            guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init " + name)
            download(guest, "builders.nix")
            guest.command(f"echo '(import ./builders.nix {{}}).second.systems.{name}' > /tmp/system.nix")
            download(guest, name + ".nvram", "/tmp/boot.nvram", private=True)
            guest.command("dd -if /tmp/boot.nvram -of /dev/sdF0/nvram -bs 126 -count 1")
            if name == "auth":
                guest.command("rm -f /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                for identity in keys:
                    download(guest, identity + ".aes", private=True)
                    guest.command(f"mkdir /mnt/keys/{identity}; cp /tmp/{identity}.aes /mnt/keys/{identity}/aeskey")
            if name in ("build", "batch"):
                download(guest, name + ".keys", "/adm/cpu.keys", private=True)
            if name != "terminal":
                guest.command(f"mkdir -p /cfg/{name}/service")
            else:
                download(guest, "glenda.keys", "/adm/terminal.keys", private=True)
                download(guest, "bad.keys", "/adm/bad.keys", private=True)
                guest.command("echo 'cat /adm/terminal.keys > /mnt/factotum/ctl' > /rc/bin/termrc.local")
                guest.command("mkdir /tmp/project")
                download(guest, "remote-project.nix", "/tmp/project/default.nix")
                download(guest, "hello.c", "/tmp/project/hello.c")
                download(guest, "delay.c", "/tmp/project/delay.c")
            guest.command("nix9-rebuild switch /tmp/system.nix")
            systems[name] = paths(guest.command(f"cat {ROOTS}/machines/{name}/system"))[0]
            if name != "terminal":
                guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    @contextmanager
    def start(name):
        address = {"auth": "10.0.2.100", "build": "10.0.2.101", "batch": "10.0.2.103"}.get(name)
        forwards = [(host, port) for peer, port, host in peers if peer == address]
        for host, _ in forwards:
            reservations[host].close()
        with boot(qemu, disks[name], snapshot=False, configure_network=False, cpu=name != "terminal",
                  prompt=PROMPT, forward_ports=forwards, guest_forwards=peers) as guest:
            guest.child.timeout = 120
            guest.command(". /usr/local/pkg/nix9/system")
            if name != "terminal":
                port = 567 if name == "auth" else 17019
                until(guest, "netstat -n | grep 'Listen *" + str(port) + " '")
            yield guest

    auth = stack.enter_context(start("auth"))
    builders = ExitStack()
    stack.callback(builders.close)
    build = builders.enter_context(start("build"))
    batch = stack.enter_context(start("batch"))
    terminal = stack.enter_context(start("terminal"))
    terminal.child.timeout = 180

    def build_project(attribute, options=""):
        output = terminal.command(f"nix-build /tmp/project -A {attribute} --no-out-link {options}")
        found = paths(output)
        if len(found) != 1:
            raise RuntimeError(f"missing remote output: {output}")
        return found[0], output

    evaluated = terminal.command("nix-instantiate --eval --strict --json --expr '(import /tmp/project {}).hello.remotePayload'")
    input_path = json.loads(re.findall(r'(?m)^"/usr/local/nix/store/[^\n]+"$', evaluated)[0])
    build.command("test ! -e " + input_path)
    hello_drv = paths(terminal.command("nix-instantiate /tmp/project -A hello"))[0]
    output_path = paths(terminal.command("nix-store -q --outputs " + hello_drv))[0]
    build.command("test ! -e " + output_path)
    result, log = build_project("hello")
    if result != output_path or " on 'cpu://" not in log or "remote-log-remote-hello" not in log:
        raise RuntimeError(f"not a scheduled remote build: {log}")
    terminal.command(result + "/bin/hello", "hello from a remote Nix builder")
    terminal.command("cat " + result + "/builder", "build")
    build.command("nix-store --verify-path " + result)
    terminal.command("nix-store --verify-path " + result)
    terminal.command("cat " + result + "/input", "input created on the terminal")
    input_path = paths(terminal.command("cat " + result + "/input-path"))[0]
    build.command("nix-store --check-validity " + input_path)
    if not re.search(r"tr-ok glenda@glenda.* -> glenda@build", auth.command("cat /sys/log/auth")):
        raise RuntimeError("remote builder bypassed the authentication server")
    print("PASS: authenticated remote compilation, input transfer, result registration and logs", flush=True)

    batch_result, _ = build_project("batch")
    terminal.command("cat " + batch_result + "/builder", "batch")
    parallel = terminal.command("nix-build /tmp/project -A parallelOne -A parallelTwo --no-out-link")
    parallel_paths = paths(parallel)
    if len(parallel_paths) != 2:
        raise RuntimeError(f"missing parallel outputs: {parallel}")
    hosts = [terminal.command("cat " + path + "/builder") for path in parallel_paths]
    if not all(any(re.search(r"(?m)^" + name + "$", record) for record in hosts) for name in ("build", "batch")):
        raise RuntimeError(f"pool did not use both one-slot builders: {hosts}")
    print("PASS: system features and concurrent scheduling across two CPU servers", flush=True)

    pooled = terminal.command("nix-build /tmp/project -A pooledOne -A pooledTwo --no-out-link "
                               "--builders 'cpu://build x86_64-plan9 - 2'")
    pooled_paths = paths(pooled)
    if len(pooled_paths) != 2:
        raise RuntimeError(f"missing concurrent CPU outputs: {pooled}")
    for path in pooled_paths:
        terminal.command("cat " + path + "/builder", "build")
        build.command("nix-store --verify-path " + path)
    print("PASS: concurrent authenticated sessions safely share one CPU's store", flush=True)

    failing_drv = paths(terminal.command("nix-instantiate /tmp/project -A failing"))[0]
    failing_path = paths(terminal.command("nix-store -q --outputs " + failing_drv))[0]
    failed(terminal, "nix-build /tmp/project -A failing --no-out-link", "remote-intentional-failure")
    failed(terminal, "nix-store --check-validity " + failing_path)
    failed(build, "nix-store --check-validity " + failing_path)

    terminal.command("rc -c " + quote("echo $pid > /tmp/client-build.pid; exec nix-build /tmp/project -A cancel --no-out-link --builders " + quote(PRIMARY))
                     + " > /tmp/cancel.log >[2=1] &")
    until(build, "test -r /tmp/nix9-remote-cancel-pid")
    remote_pid = re.findall(r"(?m)^[0-9]+$", build.command("cat /tmp/nix9-remote-cancel-pid"))[0]
    terminal.command("clientBuildPid=`{cat /tmp/client-build.pid}; echo -n interrupt > /proc/$clientBuildPid/note")
    until(build, "test ! -e /proc/" + remote_pid)
    build.command("test ! -e /tmp/nix9-remote-cancel-leaked")
    until(terminal, "grep -s interrupted /tmp/cancel.log")
    build_project("afterCancel", "--builders " + quote(PRIMARY))
    print("PASS: failed outputs remain invalid; cancellation stops remote work and releases its slot", flush=True)

    terminal.command("echo 'delkey proto=dp9ik' > /mnt/factotum/ctl; cat /adm/bad.keys > /mnt/factotum/ctl")
    failed(terminal, "nix-build /tmp/project -A denied --no-out-link --builders cpu://build", "cannot build on")
    terminal.command("echo 'delkey proto=dp9ik' > /mnt/factotum/ctl; cat /adm/terminal.keys > /mnt/factotum/ctl")
    builders.close()
    cached, _ = build_project("hello")
    if cached != result:
        raise RuntimeError("cached result changed")
    failover, _ = build_project("failover")
    terminal.command("cat " + failover + "/builder", "batch")
    failed(terminal, "nix-build /tmp/project -A unavailable --no-out-link --builders cpu://build", "cannot build on")
    local, _ = build_project("localBuild", "--builders '' --max-jobs 1")
    terminal.command("cat " + local + "/builder", "terminal")
    print("PASS: authentication rejection, local result reuse and fallback to an available CPU", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "machines": len(NAMES), "systems": systems,
        "remoteOutput": result, "input": input_path, "parallelOutputs": parallel_paths,
        "featureOutput": batch_result, "failoverOutput": failover,
        "sameCpuOutputs": pooled_paths, "localOutput": local,
    }, indent=2) + "\n")
