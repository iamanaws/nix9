"""Use shared native NDB declarations on a dual-interface CPU and a terminal."""

from pathlib import Path
import ipaddress
import re
import secrets
import subprocess

from guest import boot, files_guest


ROOTS = "/usr/local/nix/state/gcroots"
PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"


def records(guest):
    queries = [
        ("sys compute ip", "10.0.2.15"),
        ("ip 10.0.2.15 ipgw", "10.0.2.2"),
        ("ip 172.23.0.10 ipgw", "172.23.0.1"),
        ("ip 172.23.0.10 ether", "525400123457"),
        ("-i sys lab-probe fs", "files-lab.example.test"),
        ("-i sys lab-probe auth", "auth-lab.example.test"),
        ("-i sys lab-probe cpu", "cpu"),
        ("-i sys lab-probe ntp", "time.example.test"),
        ("-i sys site-probe fs", "files-site.example.test"),
        ("-i sys terminal fs", "files-workstation.example.test"),
        ("authdom partner.example.test auth", "192.0.2.12"),
        ("tcp artifacts port", "17050"),
        ("dom example.test ns", "ns.example.test"),
        ("mx mail1.example.test pref", "10"),
        ("mx mail2.example.test pref", "20"),
        ("sys ipv6-example ip", "2001:db8::10"),
        ("sys raw-record ip", "192.0.2.201"),
        ("sys record-values description", "build cache #1"),
        ("-m sys record-values tag", "first"),
    ]
    for query, expected in queries:
        guest.command("ndb/query " + query, expected)
    if not re.search(r"(?m)^second\r?$", guest.command("ndb/query -m sys record-values tag")):
        raise RuntimeError("repeated structured attributes were lost")
    result = guest.command("ndb/query tcp artifacts authdom")
    if re.search(r"(?m)^partner\.example\.test$", result):
        raise RuntimeError("separate native records were joined into one tuple")


def live(guest, address):
    result = guest.command("ndb/csquery /net/cs tcp!build-cache!artifacts")
    if address + "!17050" not in result:
        raise RuntimeError("booted cs used a different generation's include: " + result)
    guest.command("nix9 status --health", guest.name + " health-result ok")


def interface(guest, name, address):
    guest.command(f"ndb/query -f /net/ndb sys {name} ip", address)
    result = guest.command(f"ndb/query -f /net/ndb sys {name} ipmask")
    masks = re.findall(r"(?m)^([0-9.]+|/[0-9]+)$", result)
    if len(masks) != 1:
        raise RuntimeError("missing interface mask: " + result)
    mask = masks[0].lstrip("/")
    if mask.isdecimal() and int(mask) >= 96:
        mask = str(int(mask) - 96)
    if ipaddress.IPv4Network("0.0.0.0/" + mask).prefixlen != 24:
        raise RuntimeError("site defaults changed the interface's network mask: " + result)


def reject(guest, command, expected):
    result = guest.command(command + "; echo NDB-ERROR:$status")
    if not re.search(r"(?m)^NDB-ERROR:.+", result) or expected not in result:
        raise RuntimeError("invalid NDB configuration was accepted: " + result)


def check_multinet(qemu, image, archive, work):
    base = Path(__file__).with_name("ndb-multinet.nix")
    disks = {}
    for name in ("cpu", "terminal"):
        disk = work / ("multinet-" + name + ".qcow2")
        if disk.exists():
            raise RuntimeError("refusing to overwrite an existing VM: " + str(disk))
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                        "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
        disks[name] = disk
        nvram = work / (name + ".nvram")
        fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
                  b"site.example.test".ljust(48, b"\0"), secrets.token_bytes(16))
        nvram.write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
        nvram.chmod(0o600)
        with files_guest(qemu, disk, {"bootstrap.tar": archive, "ndb-multinet.nix": base,
                                     "boot.nvram": nvram},
                         snapshot=False, compress=True) as guest:
            guest.child.timeout = 900
            guest.command("cd / && tar xf /tmp/bootstrap.tar; . /usr/local/pkg/nix9/activate")
            guest.command("nix9 init " + name)
            guest.command("chmod 600 /tmp/boot.nvram; dd -if /tmp/boot.nvram -of /dev/sdF0/nvram -bs 126 -count 1; rm /tmp/boot.nvram")
            if name == "cpu":
                guest.command("mkdir -p /cfg/cpu/service")
            guest.command(f"nix-build /tmp/ndb-multinet.nix -A initial.build --out-link {ROOTS}/ndb-installation")
            guest.command(f"bundle=`{{cat {ROOTS}/ndb-installation}}; nix9 select $bundle/systems/{name}")
            if name == "cpu":
                guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    cpu_options = dict(snapshot=False, configure_network=False, cpu=True, prompt=PROMPT,
                       extra_nics=("user,net=172.23.0.0/24",))
    with boot(qemu, disks["cpu"], **cpu_options) as guest:
        guest.name = "cpu"
        guest.child.timeout = 300
        guest.command(". /usr/local/pkg/nix9/system")
        records(guest)
        guest.command("ndb/query -m sys cpu ip", "10.0.2.15")
        guest.command("ndb/query sys ordered ip", "192.0.2.81")
        interface(guest, "cpu", "10.0.2.15")
        if "172.23.0.10" not in guest.command("cat /net/ipselftab"):
            raise RuntimeError("the secondary interface was not configured")
        live(guest, "192.0.2.80")
        selected = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command(f"cat {ROOTS}/machines/cpu/system"))[0]
        for case, expected in [("missingFile", "undeclared files"),
                               ("duplicateAlias", "aliases"),
                               ("duplicateExtraAddress", "duplicate IPv4"),
                               ("invalidGateway", "ipgw"),
                               ("invalidRecordValue", "records"),
                               ("emptyRecordLines", "records"),
                               ("overriddenAddress", "owns NDB primary"),
                               ("removedHost", "owns NDB primary")]:
            reject(guest, f"nix-build /tmp/ndb-multinet.nix -A {case}.systems.cpu --out-link {ROOTS}/ndb-invalid", expected)
        guest.command(f"cat {ROOTS}/machines/cpu/system", selected)
        guest.command(f"nix-build /tmp/ndb-multinet.nix -A missingRuntime.systems.cpu --out-link {ROOTS}/ndb-missing")
        reject(guest, f"nix9 check {ROOTS}/ndb-missing", "unreadable NDB include")
        guest.command("ndb/query sys build-cache ip", "192.0.2.80")
        guest.command(f"nix-build /tmp/ndb-multinet.nix -A changed.systems.cpu --out-link {ROOTS}/ndb-next")
        guest.command(f"nix9 select {ROOTS}/ndb-next; . /usr/local/pkg/nix9/system")
        guest.command("ndb/query sys build-cache ip", "192.0.2.90")
        guest.command("ndb/query sys ordered ip", "192.0.2.91")
        live(guest, "192.0.2.80")
        guest.command("nix-store --gc")
        live(guest, "192.0.2.80")
        print("PASS: native tuple grouping, aliases, host/subnet/site defaults, ordered includes and unchanged booted cs through selection/GC", flush=True)
    with boot(qemu, disks["cpu"], **cpu_options) as guest:
        guest.name = "cpu"
        guest.command(". /usr/local/pkg/nix9/system")
        records(guest)
        live(guest, "192.0.2.90")
        guest.command("nix9-rebuild rollback; . /usr/local/pkg/nix9/system")
        guest.command("ndb/query sys build-cache ip", "192.0.2.80")
        live(guest, "192.0.2.90")
    with boot(qemu, disks["cpu"], **cpu_options) as guest:
        guest.name = "cpu"
        guest.command(". /usr/local/pkg/nix9/system")
        live(guest, "192.0.2.80")
    with boot(qemu, disks["terminal"], snapshot=False, configure_network=False,
              prompt=PROMPT, network_options=("net=172.23.0.0/24",)) as guest:
        guest.name = "terminal"
        guest.command(". /usr/local/pkg/nix9/system")
        records(guest)
        live(guest, "192.0.2.80")
        interface(guest, "terminal", "172.23.0.20")
    print("PASS: shared NDB on two networks, fresh boot, reboot/rollback and health checks on both machines", flush=True)
