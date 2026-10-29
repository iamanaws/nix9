"""Boot configured networking without harness ipconfig; exercise DNS and rollback."""

import contextlib
import functools
import http.server
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

from guest import boot, files_guest


SYSTEM = "/usr/local/nix/state/gcroots/machines/test/system"
REMOTE = "10.0.2.200"  # Outside the static guest's /25: requires its default route.
PAYLOAD = "nix9 declarative networking download"
INVALID = {
    "invalidEnable": "enable", "invalidInterface": "interface", "invalidDHCP": "useDHCP",
    "mixedAddress": "useDHCP", "mixedPrefix": "useDHCP", "missingAddress": "address",
    "invalidAddress": "address", "loopbackAddress": "address", "multicastAddress": "address",
    "missingPrefix": "prefixLength", "invalidPrefix": "prefixLength",
    "invalidGateway": "defaultGateway", "invalidDNS": "nameservers",
    "invalidDNSList": "nameservers", "ambiguousDNS": "nameservers",
}


def root(guest):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"cat {SYSTEM}"))
    if len(paths) != 1:
        raise RuntimeError(f"missing system root: {paths}")
    return paths[0]


def network(guest, address, prefix, dns):
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("echo `{cat /dev/sysname}", "nix9-network")
    # Native NDB is preserved; dynamic interface records come from ipconfig.
    guest.command("cmp /lib/ndb/local /tmp/original-ndb")
    guest.command("test -r /net/cs && test -r /net/dns")
    guest.command("ndb/query -f /net/ndb sys nix9-network ip", address)
    masks = re.findall(r"(?m)^([0-9.]+|/[0-9]+)$", guest.command("ndb/query -f /net/ndb sys nix9-network ipmask"))
    if len(masks) != 1:
        raise RuntimeError(f"missing IPv4 netmask: {masks}")
    mask = masks[0].lstrip("/")
    # Static ipconfig writes IPv4-mapped prefixes; DHCP can include dotted masks.
    if mask.isdecimal() and int(mask) >= 96:
        mask = str(int(mask) - 96)
    if ipaddress.IPv4Network("0.0.0.0/" + mask).prefixlen != prefix:
        raise RuntimeError(f"incorrect IPv4 netmask: {masks}")
    guest.command("ndb/query -f /net/ndb sys nix9-network ipgw", "10.0.2.2")
    guest.command("ndb/query -f /net/ndb sys nix9-network dns", dns)
    table = guest.command("cat /net/ipselftab")
    for ip in (address, "127.0.0.1", "::1"):
        if not re.search(r"(?m)^" + re.escape(ip) + r"\s+.*[46]u\s*$", table):
            raise RuntimeError(f"missing local address {ip}: {table}")
    routes = guest.command("cat /net/iproute")
    if not re.search(r"(?m)^0\.0\.0\.0\s+/96\s+10\.0\.2\.2\s+4", routes):
        raise RuntimeError(f"missing default route: {routes}")


def download(guest, host, port):
    # hget otherwise accepts an existing file after checking only its length.
    guest.command("echo -n > /tmp/download")
    guest.command(f"hget -o /tmp/download http://{host}:{port}/payload")
    guest.command("cat /tmp/download", PAYLOAD)


def dns_download(guest, port):
    # A separate native authoritative server supplies deterministic UDP DNS.
    # Bind the kernel stack, not /net's union containing the managed resolver.
    # No test command configures an interface on these boots.
    guest.command("mkdir -p /n/dns-fixture; bind '#I' /n/dns-fixture")
    guest.command("ndb/dns -R -x /n/dns-fixture -f /tmp/dns.ndb -s 127.0.0.1")
    answer = guest.command("echo 'fixture.nix9.test ip' | ndb/dnsquery; echo ''")
    if not re.search(r"fixture\.nix9\.test ip\s+" + re.escape(REMOTE), answer):
        raise RuntimeError(f"managed resolver failed: {answer}")
    download(guest, "fixture.nix9.test", port)


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_NETWORK_TEST_STATE")
with (contextlib.nullcontext(state) if state else tempfile.TemporaryDirectory()) as directory:
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "network.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    fixtures = {"bootstrap.tar": archive, "networks.nix": Path(__file__).with_name("networks.nix")}
    with files_guest(qemu, disk, fixtures, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix9-rebuild init test")
        guest.command("cp /lib/ndb/local /tmp/original-ndb")
        guest.command("echo 'dom=nix9.test soa= ns=ns.nix9.test' > /tmp/dns.ndb")
        guest.command("echo 'dom=ns.nix9.test ip=127.0.0.1' >> /tmp/dns.ndb")
        guest.command(f"echo 'dom=fixture.nix9.test ip={REMOTE}' >> /tmp/dns.ndb")
        for name in ("dhcp", "dns", "static", *INVALID):
            guest.command(f"echo '(import ./networks.nix).{name}' > /tmp/{name}.nix")
        guest.command("nix9-rebuild switch /tmp/dhcp.nix", "Network changes take effect after reboot.")
        dhcp = root(guest)
        for name, reason in INVALID.items():
            result = guest.command(f"nix9-rebuild switch /tmp/{name}.nix; echo NETWORK-ERROR:$status")
            if not re.search(r"(?m)^NETWORK-ERROR:.+", result) or "networking." + reason not in result:
                raise RuntimeError(f"invalid networking was accepted: {name}: {result}")
            if root(guest) != dhcp:
                raise RuntimeError("invalid networking changed the selected generation")
            guest.command("test ! -e '#s/nix9-system-test'")
        guest.command("rm /tmp/bootstrap.tar")
    (work / "payload").write_text(PAYLOAD + "\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        options = dict(snapshot=False, configure_network=False, prompt=r"(?m)^(?:term)?% ",
                       guest_forward=(REMOTE, port, port))
        try:
            with boot(qemu, disk, **options) as guest:
                network(guest, "10.0.2.15", 24, "10.0.2.3")
                guest.command(f"cat {SYSTEM}-boot", dhcp)
                download(guest, REMOTE, port)
                guest.command("nix9-rebuild switch /tmp/dns.nix")
                dns = root(guest)
                network(guest, "10.0.2.15", 24, "10.0.2.3")
                print("PASS: automatic DHCP, loopback, native NDB and downloads", flush=True)
            with boot(qemu, disk, **options) as guest:
                network(guest, "10.0.2.15", 24, "10.0.2.3")
                dns_download(guest, port)
                guest.command("nix9-rebuild switch /tmp/static.nix")
                static = root(guest)
                # Selection and login activation must leave the running network alone.
                network(guest, "10.0.2.15", 24, "10.0.2.3")
                print("PASS: explicit DHCP DNS overrides the offered resolver", flush=True)
            with boot(qemu, disk, **options) as guest:
                network(guest, "10.0.2.42", 25, "127.0.0.1")
                guest.command(f"cat {SYSTEM}-boot", static)
                dns_download(guest, port)
                guest.command("nix9-rebuild rollback", "Network changes take effect after reboot.")
                if root(guest) != dns:
                    raise RuntimeError("rollback did not restore the DHCP generation")
                network(guest, "10.0.2.42", 25, "127.0.0.1")
                print("PASS: static IPv4, DNS and a download through the default gateway", flush=True)
            with boot(qemu, disk, **options) as guest:
                network(guest, "10.0.2.15", 24, "10.0.2.3")
                guest.command(f"cat {SYSTEM}-boot", dns)
                dns_download(guest, port)
                print("PASS: rollback restores DHCP and DNS on reboot", flush=True)
        finally:
            server.shutdown()
            thread.join()
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "dhcpSystem": dhcp, "dnsSystem": dns, "staticSystem": static,
        "rebootsWithoutHarnessNetworking": 4, "rejectedConfigurations": list(INVALID),
        "checks": ["dhcp", "dns-override", "static-ipv4", "ipv4-and-ipv6-loopback",
                   "native-ndb-preserved", "off-subnet-download", "boot-only-changes", "rollback"],
    }, indent=2) + "\n")
