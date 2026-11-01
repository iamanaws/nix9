"""Serve generation-backed NDB records to a native client and UDP/TCP DNS clients."""

from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

from guest import boot, files_guest


ROOTS = "/usr/local/nix/state/gcroots"
PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"
ZONE = "lab.example.test"


def query(port, name, kind, *, tcp=False, status="NOERROR", authoritative=True):
    result = subprocess.run(
        ["dig", "@127.0.0.1", "-p", str(port), name, kind,
         "+tcp" if tcp else "+notcp", "+norecurse", "+noall", "+answer",
         "+authority", "+comments", "+tries=1", "+time=2"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode or f"status: {status}," not in result.stdout:
        raise RuntimeError(f"DNS {kind} {name} failed: {result.stdout}{result.stderr}")
    match = re.search(r"flags: ([^;]+);", result.stdout)
    flags = match.group(1).split() if match else []
    if authoritative and "aa" not in flags:
        raise RuntimeError("DNS answer is not authoritative: " + result.stdout)
    answers = [line.split() for line in result.stdout.splitlines()
               if line and not line.startswith(";")]
    return answers, flags


def records(port, address):
    expected = [
        ("build." + ZONE, "A", [address]),
        ("v6." + ZONE, "AAAA", ["2001:db8::30"]),
        (ZONE, "MX", ["10 mail1." + ZONE + ".", "20 mail2." + ZONE + "."]),
        (ZONE, "NS", ["ns." + ZONE + "."]),
        ("www." + ZONE, "CNAME", ["build." + ZONE + "."]),
        (".".join(reversed(address.split("."))) + ".in-addr.arpa", "PTR", ["build." + ZONE + "."]),
    ]
    for tcp in (False, True):
        for name, kind, values in expected:
            answers, _ = query(port, name, kind, tcp=tcp)
            actual = sorted(" ".join(row[4:]) for row in answers if row[3] == kind)
            if actual != sorted(values):
                raise RuntimeError(f"wrong {kind} answer for {name}: {answers}")
        answers, _ = query(port, ZONE, "SOA", tcp=tcp)
        if not any(row[3] == "SOA" and row[4] == "ns." + ZONE + "." for row in answers):
            raise RuntimeError("missing SOA record: " + str(answers))
        answers, _ = query(port, "absent." + ZONE, "A", tcp=tcp)
        if any(row[3] == "A" for row in answers) or not any(row[3] == "SOA" for row in answers):
            raise RuntimeError("wrong native negative answer: " + str(answers))


def recursion(port, allowed):
    for tcp in (False, True):
        _, flags = query(port, "outside.test", "A", tcp=tcp,
                         status="NOERROR" if allowed else "REFUSED", authoritative=False)
        if ("ra" in flags) != allowed:
            raise RuntimeError("unexpected recursion policy: " + str(flags))


def native_query(guest, address):
    result = guest.command("ndb/dnsdebug -f /dev/null @172.23.0.10 build." + ZONE + " ip")
    if ("rcvd 172.23.0.10" not in result or "authoritative" not in result
            or address not in result):
        raise RuntimeError("native client did not receive the authoritative answer: " + result)


def health(guest):
    guest.command("nix9 status --health", "dns health-result ok")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_DNS_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    cables = [stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) for _ in range(2)]
    for cable in cables:
        cable.bind(("127.0.0.1", 0))
    server_port, client_port = [cable.getsockname()[1] for cable in cables]
    tcp = stack.enter_context(socket.socket())
    tcp.bind(("127.0.0.1", 0))
    port = tcp.getsockname()[1]
    udp = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    udp.bind(("127.0.0.1", port))

    disks = {}
    for name in ("dns", "terminal"):
        disk = work / (name + ".qcow2")
        if disk.exists():
            raise RuntimeError("refusing to overwrite an existing VM: " + str(disk))
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                        "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
        disks[name] = disk
        with files_guest(qemu, disk, {"bootstrap.tar": archive,
                                     "dns.nix": Path(__file__).with_name("dns.nix")},
                         snapshot=False, compress=True) as guest:
            guest.child.timeout = 900
            guest.command("cd / && tar xf /tmp/bootstrap.tar && . /usr/local/pkg/nix9/activate")
            guest.command("nix9 init " + name)
            guest.command(f"nix-build /tmp/dns.nix -A initial.systems.{name} --out-link {ROOTS}/dns-system")
            guest.command(f"nix9 select {ROOTS}/dns-system")

    tcp.close()
    udp.close()
    cables[0].close()
    running = stack.enter_context(ExitStack())

    def start_server():
        guest = running.enter_context(boot(
            qemu, disks["dns"], snapshot=False, configure_network=False, prompt=PROMPT,
            network_options=(f"hostfwd=udp:127.0.0.1:{port}-:53",),
            forward_ports=((port, 53),),
            extra_nics=(f"socket,udp=127.0.0.1:{client_port},localaddr=127.0.0.1:{server_port}",),
        ))
        guest.command(". /usr/local/pkg/nix9/system")
        return guest

    def select(guest, configuration):
        guest.command(f"nix-build /tmp/dns.nix -A {configuration}.systems.dns --out-link {ROOTS}/dns-next")
        guest.command(f"nix9 select {ROOTS}/dns-next && . /usr/local/pkg/nix9/system")

    server = start_server()
    health(server)
    records(port, "172.23.0.30")
    recursion(port, False)
    health(server)
    cables[1].close()
    with boot(qemu, disks["terminal"], snapshot=False, configure_network=False, prompt=PROMPT,
              network_backend=f"socket,udp=127.0.0.1:{server_port},localaddr=127.0.0.1:{client_port}") as client:
        client.command(". /usr/local/pkg/nix9/system")
        native_query(client, "172.23.0.30")
        for case in ("badAddress", "disabledListener", "tcpConflict", "cwfsConflict"):
            result = server.command(f"nix-build /tmp/dns.nix -A {case}.systems.dns --out-link {ROOTS}/dns-invalid; echo DNS-ERROR:$status")
            if not re.search(r"(?m)^DNS-ERROR:.+", result) or "services.ndb.dns" not in result:
                raise RuntimeError("invalid DNS settings were accepted: " + result)
        select(server, "changed")
        records(port, "172.23.0.30")
        recursion(port, False)
        server.command("nix-store --gc")
        native_query(client, "172.23.0.30")
        running.close()

        server = start_server()
        records(port, "172.23.0.31")
        recursion(port, True)
        native_query(client, "172.23.0.31")
        health(server)
        server.command("nix9-rebuild rollback && . /usr/local/pkg/nix9/system")
        records(port, "172.23.0.31")
        running.close()

        server = start_server()
        records(port, "172.23.0.30")
        recursion(port, False)
        native_query(client, "172.23.0.30")
        select(server, "local")
        running.close()

        server = start_server()
        records(port, "172.23.0.30")
        recursion(port, True)
        native_query(client, "172.23.0.30")
        health(server)
        processes = [line.split()[1] for line in server.command("ps -a").splitlines()
                     if "udp server " in line and len(line.split()) > 2 and line.split()[1].isdecimal()]
        if len(processes) != 1:
            raise RuntimeError("could not identify the DNS UDP listener")
        server.command("echo kill > /proc/" + processes[0] + "/notepg")
        result = server.command("nix9 status --health; echo DNS-HEALTH:$status")
        if "health dns/udp/* failed" not in result or not re.search(r"(?m)^DNS-HEALTH:.+", result):
            raise RuntimeError("health accepted a stopped DNS server: " + result)
        select(server, "localOnly")
        running.close()

        server = start_server()
        health(server)
        server.command("test -e /net/dns")
        result = server.command("echo 'build." + ZONE + " ip' | ndb/dnsquery; echo ''")
        if "172.23.0.30" not in result:
            raise RuntimeError("local DNS stopped working after listener removal: " + result)
        for protocol in ("udp", "tcp"):
            result = server.command(f"netstat -n -p {protocol}")
            if re.search(r"(?m)^" + protocol + r"\s+\d+\s+\S+\s+(?:Listen|Open)\s+53\s", result):
                raise RuntimeError("a removed DNS listener is still active: " + result)
        failed = subprocess.run(["dig", "@127.0.0.1", "-p", str(port), "build." + ZONE,
                                 "+tries=1", "+time=1"], capture_output=True, text=True, timeout=5)
        if failed.returncode == 0:
            raise RuntimeError("DNS still answered remotely after listener removal")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "status": "passed", "machines": 2, "configured-boots": 6,
    "authoritative-udp-and-tcp": "passed", "native-network-client": "passed",
    "forward-reverse-mail-and-aliases": "passed", "recursion-policies": "passed",
    "selection-gc-reboot-and-rollback": "passed", "listener-health-and-removal": "passed",
}, indent=2) + "\n")
print("PASS: authoritative DNS over UDP/TCP, native client, recursion policies, health, GC and rollback", flush=True)
