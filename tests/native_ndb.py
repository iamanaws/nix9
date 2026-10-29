"""Build native NDB tools and exercise generation-backed discovery across boots."""

import contextlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from guest import boot, files_guest


ROOT = "/usr/local/nix/state/gcroots/machines/test/system"


def discovery(guest):
    guest.command("ndb/query sys fs1 ip", "10.0.2.2")
    guest.command("ndb/query ip 10.0.2.200 sys", "cpu1")
    guest.command("ndb/query ether 525400123456 sys", "terminal")
    result = guest.command("ndb/ipquery ip 10.0.2.15 auth fs cpu authdom")
    for value in ("auth=fs1", "fs=fs1", "cpu=cpu1", "authdom=nix9.test"):
        if value not in result:
            raise RuntimeError(f"missing inherited NDB default {value}: {result}")
    guest.command("ndb/query sys manual ip", "10.3.4.5")


def running(guest, dns):
    guest.command(". /usr/local/pkg/nix9/system")
    discovery(guest)
    result = guest.command("ndb/csquery /net/cs tcp!cpu1!17019")
    if "10.0.2.200!17019" not in result:
        raise RuntimeError(f"cs did not resolve the declared CPU service: {result}")
    if dns:
        result = guest.command("echo 'fs1.nix9.test ip' | ndb/dnsquery; echo ''")
        if "10.0.2.2" not in result:
            raise RuntimeError(f"dns did not resolve the declared file server: {result}")
    else:
        guest.command("test ! -e /srv/dns && test ! -e /net/dns")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_NDB_TEST_STATE")
fixtures = {"bootstrap.tar": archive, "ndb.nix": Path(__file__).with_name("ndb.nix")}
with (contextlib.nullcontext(state) if state else tempfile.TemporaryDirectory()) as directory:
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "ndb.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    with files_guest(qemu, disk, fixtures, snapshot=False, compress=True) as guest:
        guest.child.timeout = 900
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix9-rebuild init test")
        guest.command("echo 'sys=manual ip=10.3.4.5' >> /lib/ndb/local")
        guest.command("cp /lib/ndb/local /tmp/manual-ndb")
        for name in ("one", "two", "disabled", "invalidAddress", "duplicateAddress", "missingHost", "invalidNetwork", "invalidInclude"):
            guest.command(f"echo '(import ./ndb.nix).{name}' > /tmp/{name}.nix")
        guest.command("nix9-rebuild switch /tmp/one.nix")
        guest.command(". /usr/local/pkg/nix9/system")
        discovery(guest)
        guest.command("cmp /cfg/nix9/ndb-original /tmp/manual-ndb")
        selected = guest.command("cat " + ROOT)
        for name in ("invalidAddress", "duplicateAddress", "missingHost", "invalidNetwork", "invalidInclude"):
            result = guest.command(f"nix9-rebuild switch /tmp/{name}.nix; echo NDB-ERROR:$status")
            if not re.search(r"(?m)^NDB-ERROR:.+", result) or "services.ndb" not in result:
                raise RuntimeError(f"invalid discovery declaration was accepted: {name}: {result}")
            if guest.command("cat " + ROOT) != selected:
                raise RuntimeError("invalid discovery declaration changed the selection")
    options = dict(snapshot=False, configure_network=False, prompt=r"(?m)^(?:term)?% ")
    with boot(qemu, disk, **options) as guest:
        running(guest, True)
        guest.command("nix9-rebuild switch /tmp/two.nix")
        running(guest, True)
    with boot(qemu, disk, **options) as guest:
        running(guest, False)
        guest.command("nix9-rebuild rollback")
        running(guest, False)
    with boot(qemu, disk, **options) as guest:
        running(guest, True)
        guest.command("nix9-rebuild switch /tmp/disabled.nix")
    with boot(qemu, disk, **options) as guest:
        guest.command(". /usr/local/pkg/nix9/system")
        guest.command("ndb/query sys manual ip", "10.3.4.5")
        guest.command("value=`{ndb/query sys cpu1 ip}; echo NDB-COUNT:$#value", "NDB-COUNT:0")
        guest.command("cmp /lib/ndb/local /tmp/manual-ndb")
    # A second independent machine evaluates and uses the same declaration.
    with files_guest(qemu, image, fixtures, compress=True) as guest:
        guest.child.timeout = 900
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix9-rebuild init test")
        guest.command("echo 'sys=manual ip=10.3.4.5' >> /lib/ndb/local")
        guest.command("echo '(import ./ndb.nix).one' > /tmp/one.nix")
        guest.command("nix9-rebuild switch /tmp/one.nix")
        guest.command(". /usr/local/pkg/nix9/system")
        discovery(guest)

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "status": "passed", "machines": 2, "configured-boots": 4,
    "native-ndb-build": "passed", "discovery-and-inheritance": "passed",
    "manual-includes": "passed", "dns-disable-and-rollback": "passed",
    "invalid-configurations": 5,
}, indent=2) + "\n")
