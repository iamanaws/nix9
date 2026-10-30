"""Use a network provider's second NIC through authenticated 9P from a CPU session."""

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
DEVICE = "172.23.0.20"
PORT = 17080
ADDRESS = f"/n/labnet/tcp!{DEVICE}!{PORT}"
PAYLOAD = "lab-device-ready"


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def selected(guest, name):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$",
                       guest.command(f"cat {ROOTS}/machines/{name}/system"))
    if len(paths) != 1:
        raise RuntimeError("missing system selection")
    return paths[0]


def rejected(guest, command, reason=None):
    result = guest.command("rc -c " + quote(command) + "; echo LAB-ERROR:$status")
    if (not re.search(r"(?m)^LAB-ERROR:.+", result) or "syntax error" in result
            or (reason and reason not in result)):
        raise RuntimeError(f"operation was not rejected: {command}: {result}")
    return result


def stop(guest):
    guest.child.sendline("fshalt")
    guest.child.expect("done halting")
    guest.crash()


def listening(guest, ports):
    deadline = time.monotonic() + 20
    while True:
        table = guest.command("netstat -n")
        if all(re.search(r"(?m)^tcp\s+\d+\s+\S+\s+Listen\s+" + str(port) + r"\s", table)
               for port in ports):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"listeners did not start: {table}")
        time.sleep(0.1)


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_NETWORK_SERVER_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("network-server.nix"), work / "network-server.nix")
    keys = {name: secrets.token_bytes(16) for name in ("auth", "labnet", "cpu", "glenda")}
    for name, roles in {"auth": ["server"], "labnet": ["server"],
                        "cpu": ["server", "speakfor"], "glenda": ["client"]}.items():
        commands = "".join(f"key proto=dp9ik dom=nix9.lab user={name} role={role} "
                           f"!hex={keys[name].hex()} !password=______\n" for role in roles)
        for suffix, data in (("keys", commands.encode()), ("aes", keys[name])):
            file = work / f"{name}.{suffix}"
            file.write_bytes(data)
            file.chmod(0o600)
    for name in ("auth", "labnet", "cpu", "terminal", "device"):
        domain = b"nix9.lab" if name == "auth" else b"bootstrap.invalid"
        fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
                  domain.ljust(48, b"\0"), secrets.token_bytes(16))
        nvram = work / (name + ".nvram")
        nvram.write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
        nvram.chmod(0o600)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    http = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
    http_thread = threading.Thread(target=http.serve_forever, daemon=True)
    http_thread.start()
    stack.callback(http_thread.join)
    stack.callback(http.shutdown)
    base = f"http://10.0.2.2:{http.server_port}"
    cables = [stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) for _ in range(2)]
    for cable in cables:
        cable.bind(("127.0.0.1", 0))
    device_port, provider_port = [cable.getsockname()[1] for cable in cables]

    def download(guest, name, destination=None, private=False):
        destination = destination or "/tmp/" + name
        if private:
            guest.command(f"echo -n > {destination}; chmod 600 {destination}")
        guest.command(f"hget -o {destination} {base}/{name}")

    peers, reservations = [], {}
    for address, port in (("10.0.2.100", 567), ("10.0.2.101", 17019),
                          ("10.0.2.103", 17020), ("10.0.2.103", 17021), ("10.0.2.103", 17022)):
        reservation = stack.enter_context(socket.socket())
        reservation.bind(("127.0.0.1", 0))
        host_port = reservation.getsockname()[1]
        peers.append((address, port, host_port))
        reservations[host_port] = reservation

    foundation = work / "bootstrap.qcow2"
    if foundation.exists():
        raise RuntimeError(f"refusing to overwrite an existing VM: {foundation}")
    qemu_img = str(Path(qemu).with_name("qemu-img"))
    subprocess.run([qemu_img, "create", "-f", "qcow2", "-F", "qcow2",
                    "-b", str(Path(image).resolve()), str(foundation)], check=True)
    with boot(qemu, foundation, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix-build '<nix9>' -A auth -A rcpu -A ndb -A listen -A exportfs -A namespaceTools "
                      "-A dial --out-link " + ROOTS + "/network-tools")
    disks, systems = {}, {}
    for name in ("auth", "labnet", "cpu", "terminal", "device"):
        disk = work / f"{name}.qcow2"
        subprocess.run([qemu_img, "create", "-f", "qcow2", "-F", "qcow2",
                        "-b", str(foundation.resolve()), str(disk)], check=True)
        disks[name] = disk
        with boot(qemu, disk, snapshot=False) as guest:
            guest.child.timeout = 900
            guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init " + name)
            download(guest, "network-server.nix")
            for configuration in (name, "moved", "disabled"):
                guest.command(f"echo '(import ./network-server.nix {{}}).{configuration}' > /tmp/{configuration}.nix")
            download(guest, name + ".nvram", "/tmp/boot.nvram", private=True)
            guest.command("dd -if /tmp/boot.nvram -of /dev/sdF0/nvram -bs 126 -count 1")
            if name == "auth":
                guest.command("rm -f /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                for identity in keys:
                    download(guest, identity + ".aes", private=True)
                    guest.command(f"mkdir /mnt/keys/{identity}; cp /tmp/{identity}.aes /mnt/keys/{identity}/aeskey")
            if name in ("auth", "labnet", "cpu"):
                download(guest, name + ".keys", "/adm/" + name + ".keys", private=True)
            if name != "terminal":
                guest.command(f"mkdir -p /cfg/{name}/service")
            if name == "terminal":
                download(guest, "glenda.keys", "/adm/terminal.keys", private=True)
                guest.command("echo 'cat /adm/terminal.keys > /mnt/factotum/ctl' > /rc/bin/termrc.local")
            guest.command(f"nix9-rebuild switch /tmp/{name}.nix")
            systems[name] = selected(guest, name)
            if name != "terminal":
                guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; "
                              "echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    @contextmanager
    def start(name):
        address = {"auth": "10.0.2.100", "cpu": "10.0.2.101", "labnet": "10.0.2.103"}.get(name)
        forwards = [(host, port) for peer, port, host in peers if peer == address]
        for host, _ in forwards:
            reservations[host].close()
        # A point-to-point Ethernet cable joins only these two NICs.
        options = dict(guest_forwards=peers, forward_ports=forwards, network_options=("restrict=on",))
        extra = ()
        if name == "device":
            cables[0].close()
            options = dict(network_backend=f"socket,udp=127.0.0.1:{provider_port},localaddr=127.0.0.1:{device_port}")
        if name == "labnet":
            cables[1].close()
            extra = (f"socket,udp=127.0.0.1:{device_port},localaddr=127.0.0.1:{provider_port}",)
        with boot(qemu, disks[name], snapshot=False, configure_network=False,
                  cpu=name != "terminal", prompt=PROMPT, extra_nics=extra, **options) as guest:
            guest.child.timeout = 600
            guest.command(". /usr/local/pkg/nix9/activate")
            yield guest

    auth = stack.enter_context(start("auth"))
    listening(auth, (567,))
    device = stack.enter_context(start("device"))
    listening(device, (PORT,))
    provider = stack.enter_context(start("labnet"))
    listening(provider, (17020, 17021, 17022))
    provider.command("grep 172.23.0.10 /net/ipselftab")
    provider.command("ndb/query -f /net/ndb sys labnet ip", "10.0.2.15")
    provider.command("grep 'device /net/ether1 ' /net/ipifc/*/status")
    cpu = stack.enter_context(start("cpu"))
    listening(cpu, (17019,))
    terminal = stack.enter_context(start("terminal"))
    terminal.command(". /usr/local/pkg/nix9/system")
    terminal.command("whatis aux/timesync", "/bin/aux/timesync")
    terminal.command("test -x /bin/aux/acpi")

    def dial(guest, prefix=""):
        guest.command(prefix + "echo status | dial -e " + ADDRESS, PAYLOAD)

    def remote(command, expected=None):
        return terminal.command("rcpu -h cpu -c " + quote(command), expected)

    for guest in (terminal, cpu):
        rejected(guest, f"alarm 2 dial -e tcp!{DEVICE}!{PORT} < /dev/null")
    dial(terminal)
    remote("echo status | dial -e " + ADDRESS, PAYLOAD)
    records = auth.command("cat /sys/log/auth")
    if not re.search(r"tr-ok glenda@cpu.* -> glenda@labnet", records):
        raise RuntimeError("CPU did not use delegated authentication for the network provider")
    print("PASS: two physical interfaces, primary discovery, direct access denied, terminal and delegated CPU network access", flush=True)

    rejected(terminal, "alarm 3 tlsclient -a -k 'dom=nix9.lab' tcp!labnet!17021 "
                      "/bin/mount -nc /fd/0 /n/labrestricted")
    terminal.command("alarm 3 tlsclient -a -k 'dom=nix9.lab' tcp!labnet!17022 "
                     "/bin/mount -nc /fd/0 /n/labreadonly")
    rejected(terminal, f"echo status | dial -e /n/labreadonly/tcp!{DEVICE}!{PORT}", "read only")
    print("PASS: native network control writes, export permissions and read-only rejection", flush=True)

    provider.command("nix9-rebuild switch /tmp/moved.nix")
    moved = selected(provider, "labnet")
    provider.command("grep 172.23.0.10 /net/ipselftab")
    remote("echo status | dial -e " + ADDRESS, PAYLOAD)
    stop(provider)
    provider = stack.enter_context(start("labnet"))
    listening(provider, (17020,))
    provider.command("grep 172.23.0.11 /net/ipselftab")
    provider.command("ndb/query -f /net/ndb sys labnet ip", "10.0.2.15")
    remote("echo status | dial -e " + ADDRESS, PAYLOAD)
    provider.command("nix9-rebuild rollback")
    stop(provider)
    provider = stack.enter_context(start("labnet"))
    listening(provider, (17020,))
    provider.command("grep 172.23.0.10 /net/ipselftab")
    remote("echo status | dial -e " + ADDRESS, PAYLOAD)
    print("PASS: secondary address changes at boot, new-session reconnection and network rollback", flush=True)

    provider.command("nix9-rebuild switch /tmp/disabled.nix")
    stop(provider)
    provider = stack.enter_context(start("labnet"))
    rejected(terminal, "rcpu -h cpu -c 'echo BAD-SESSION > /tmp/bad-lab-session'", "required share is unavailable")
    cpu.command("test ! -e /tmp/bad-lab-session")
    stop(cpu)
    cpu = stack.enter_context(start("cpu"))
    listening(cpu, (17019,))
    provider.command("nix9-rebuild select " + systems["labnet"])
    stop(provider)
    provider = stack.enter_context(start("labnet"))
    listening(provider, (17020,))
    remote("echo status | dial -e " + ADDRESS, PAYLOAD)
    print("PASS: provider failure blocks required sessions, CPU boots independently, and access recovers after reboot", flush=True)

    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "machines": 5, "providerBoots": 5, "cpuBoots": 2,
        "systems": systems, "movedSystem": moved,
        "checks": ["bundled-example", "two-nics", "primary-ndb", "secondary-static-address",
                   "no-direct-lab-route", "remote-network-tree", "terminal-dial", "delegated-cpu-dial",
                   "native-aux-preserved", "allowed-users", "read-only-control-rejection", "boot-only-network-changes",
                   "provider-reboot", "rollback", "required-provider-failure", "independent-cpu-boot", "recovery"],
    }, indent=2) + "\n")
