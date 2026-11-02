"""Negotiate and renew native DHCP leases across server generations and reboots."""

from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from guest import boot, files_guest
from ethernet import Ethernet


ROOTS = "/usr/local/nix/state/gcroots"
PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"


def wait_for(description, check, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(1)
    raise RuntimeError("timed out waiting for " + description)


def learned(guest, name, address=None):
    result = guest.command(f"ndb/query -f /net/ndb sys {name} ip")
    matches = re.findall(r"(?m)^(172\.23\.0\.\d+)$", result)
    if len(matches) != 1 or (address is not None and matches[0] != address):
        raise RuntimeError("wrong DHCP address: " + result)
    address = matches[0]
    for attribute, expected in {
        "ipmask": "255.255.255.0", "ipgw": "172.23.0.1", "dns": "172.23.0.10",
        "dnsdomain": "lab.example.test", "fs": "172.23.0.11", "auth": "172.23.0.12",
        "ntp": "172.23.0.13",
    }.items():
        guest.command(f"ndb/query -f /net/ndb ip {address} {attribute}", expected)
    answer = guest.command("ndb/dnsdebug -f /dev/null @172.23.0.10 build.lab.example.test ip")
    if "rcvd 172.23.0.10" not in answer or "172.23.0.30" not in answer:
        raise RuntimeError("DHCP client could not use the native DNS server: " + answer)
    return address


def lease(guest, address):
    result = guest.command("cat /lib/ndb/dhcp/" + address)
    match = re.search(r"(?m)^(\d{9,})\n([^\n]+)\n", result)
    if not match:
        raise RuntimeError("invalid persistent DHCP lease: " + result)
    return int(match[1]), match[2]


def ack(network, mac, address, since=0, renewal=False):
    return any(message["type"] == 5 and message["mac"] == mac
               and message["yiaddr"] == address and message["server"] == "172.23.0.10"
               and (not renewal or message["ciaddr"] == address)
               for message in network.captured()[since:])


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_DHCP_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    network = Ethernet(("dns", "terminal", "visitor"))
    stack.callback(network.close)
    disks = {}
    for name in ("dns", "terminal", "visitor"):
        disk = work / (name + ".qcow2")
        if disk.exists():
            raise RuntimeError("refusing to overwrite an existing VM: " + str(disk))
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                        "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
        disks[name] = disk
        with files_guest(qemu, disk, {"bootstrap.tar": archive,
                                     "dhcpd.nix": Path(__file__).with_name("dhcpd.nix")},
                         snapshot=False, compress=True) as guest:
            guest.child.timeout = 900
            guest.command("cd / && tar xf /tmp/bootstrap.tar && . /usr/local/pkg/nix9/activate")
            guest.command("nix9 init " + name)
            attribute = "visitor" if name == "visitor" else "initial.systems." + name
            guest.command(f"nix-build /tmp/dhcpd.nix -A {attribute} --out-link {ROOTS}/dhcp-system")
            guest.command(f"nix9 select {ROOTS}/dhcp-system")

    server_run = stack.enter_context(ExitStack())
    client_run = stack.enter_context(ExitStack())

    def start_server():
        guest = server_run.enter_context(boot(
            qemu, disks["dns"], snapshot=False, configure_network=False, prompt=PROMPT,
            extra_nics=(network.backend("dns", "52:54:00:12:34:57"),),
        ))
        guest.command(". /usr/local/pkg/nix9/system")
        return guest

    def start_client():
        guest = client_run.enter_context(boot(
            qemu, disks["terminal"], snapshot=False, configure_network=False, prompt=PROMPT,
            network_backend=network.backend("terminal", "52:54:00:12:34:56"),
        ))
        guest.command(". /usr/local/pkg/nix9/system")
        return guest

    def select(guest, configuration):
        guest.command(f"nix-build /tmp/dhcpd.nix -A {configuration}.systems.dns --out-link {ROOTS}/dhcp-next")
        guest.command(f"nix9 select {ROOTS}/dhcp-next && . /usr/local/pkg/nix9/system")

    server = start_server()
    server.command("nix9 status --health", "dns health-result ok")
    client = start_client()
    learned(client, "terminal", "172.23.0.20")
    wait_for("reserved client lease renewal", lambda: ack(network, "525400123456", "172.23.0.20", renewal=True))

    with boot(qemu, disks["visitor"], snapshot=False, configure_network=False, prompt=PROMPT,
              network_backend=network.backend("visitor", "52:54:00:12:34:58")) as visitor:
        visitor.command(". /usr/local/pkg/nix9/system")
        address = learned(visitor, "visitor")
        if not 100 <= int(address.rsplit(".", 1)[1]) <= 119:
            raise RuntimeError("dynamic client received an address outside its pool")
        initial_lease = lease(server, address)
        server.command("ip/dhcpleases | grep '^" + address.replace(".", "[.]") + " leased by '")
        wait_for("dynamic client lease renewal", lambda: lease(server, address)[0] > initial_lease[0])
        if lease(server, address)[1] != initial_lease[1]:
            raise RuntimeError("renewal changed the lease owner")
        if not ack(network, "525400123458", address, renewal=True):
            raise RuntimeError("lease file changed without a DHCP renewal acknowledgment")

        server.command("chmod 555 /lib/ndb/dhcp")
        result = server.command("nix9 status --health; echo DHCP-HEALTH:$status")
        if "health dhcpd/leases failed" not in result or not re.search(r"(?m)^DHCP-HEALTH:.+", result):
            raise RuntimeError("health accepted an unwritable lease directory: " + result)
        server.command("chmod 775 /lib/ndb/dhcp")

        for case in ("badAddress", "overlap", "reservationConflict"):
            result = server.command(f"nix-build /tmp/dhcpd.nix -A {case}.systems.dns --out-link {ROOTS}/dhcp-invalid; echo DHCP-ERROR:$status")
            if not re.search(r"(?m)^DHCP-ERROR:.+", result) or "services.dhcpd" not in result:
                raise RuntimeError("invalid DHCP settings were accepted: " + result)

        select(server, "changed")
        server.command("nix-store --gc")
        position = len(network.captured())
        wait_for("booted reservation after selection and GC", lambda: ack(network, "525400123456", "172.23.0.20", position, renewal=True))
        client_run.close()
        before_restart = lease(server, address)
        server_run.close()

        server = start_server()
        server.command("nix9 status --health", "dns health-result ok")
        if lease(server, address)[1] != before_restart[1]:
            raise RuntimeError("server restart lost the lease owner")
        position = len(network.captured())
        wait_for("dynamic renewal after server restart", lambda: ack(network, "525400123458", address, position, renewal=True))
        client = start_client()
        learned(client, "terminal", "172.23.0.21")
        server.command("nix9-rebuild rollback && . /usr/local/pkg/nix9/system")
        position = len(network.captured())
        wait_for("booted reservation after rollback selection", lambda: ack(network, "525400123456", "172.23.0.21", position, renewal=True))
        client_run.close()
        server_run.close()

        server = start_server()
        server.command("nix9 status --health", "dns health-result ok")
        position = len(network.captured())
        wait_for("dynamic renewal after rollback reboot", lambda: ack(network, "525400123458", address, position, renewal=True))
        if lease(server, address)[1] != initial_lease[1]:
            raise RuntimeError("rollback lost the persistent lease owner")
        client = start_client()
        learned(client, "terminal", "172.23.0.20")

        processes = [line.split()[1] for line in server.command("ps -a").splitlines()
                     if re.search(r"\bdhcpd\s*$", line) and len(line.split()) > 2 and line.split()[1].isdecimal()]
        if len(processes) != 1:
            raise RuntimeError("could not identify the DHCP daemon")
        server.command("echo kill > /proc/" + processes[0] + "/notepg")
        result = server.command("nix9 status --health; echo DHCP-HEALTH:$status")
        if "health dhcpd/listener failed" not in result or not re.search(r"(?m)^DHCP-HEALTH:.+", result):
            raise RuntimeError("health accepted a stopped DHCP server: " + result)
        select(server, "disabled")
        client_run.close()
        server_run.close()
        server = start_server()
        server.command("nix9 status --health", "dns health-result ok")
        result = server.command("netstat -n -p udp")
        if re.search(r"(?m)^udp\s+\d+\s+\S+\s+Open\s+67\s", result):
            raise RuntimeError("a removed DHCP listener is still active: " + result)
        server.command("test -f /lib/ndb/dhcp/" + address)

    captured = network.captured()
    for mac in ("525400123456", "525400123458"):
        if not {1, 3, 5}.issubset({message["type"] for message in captured if message["mac"] == mac}):
            raise RuntimeError("missing native DHCP discover, request or acknowledgment")

Path(output).mkdir()
Path(output, "dhcp-messages.json").write_text(json.dumps(captured, indent=2) + "\n")
Path(output, "results.json").write_text(json.dumps({
    "status": "passed", "machines": 3, "server-boots": 4, "reserved-client-boots": 3,
    "reservations-and-dynamic-pools": "passed", "ndb-defaults-and-dns": "passed",
    "native-lease-renewal": "passed", "persistent-leases-and-server-restart": "passed",
    "selection-gc-reboot-and-rollback": "passed", "listener-health-and-removal": "passed",
}, indent=2) + "\n")
print("PASS: native DHCP reservations, pools, NDB defaults, renewal, persistent leases, GC and rollback", flush=True)
