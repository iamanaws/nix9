"""Exercise system generations through native CPU-server startup and login."""

from contextlib import ExitStack, nullcontext
import functools
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time

from guest import boot
from ntp import NTP, OFFSET


SYSTEM = "/usr/local/nix/state/gcroots/system"
CPU_HOOK = "/rc/bin/cpurc.local"
CPU_PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"


def root(guest):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"cat {SYSTEM}"))
    if len(paths) != 1:
        raise RuntimeError(f"missing selected system: {paths}")
    return paths[0]


def clock(guest, arguments):
    lines = [line for line in guest.command("ps -a").splitlines()
             if re.search(r"\btimesync(?:\s|$)", line)]
    if len(lines) != 1:
        raise RuntimeError(f"expected one native timesync: {lines}")
    guest.command("cat /tmp/timesync-invocation", "timesync " + " ".join(arguments))
    return lines[0].split()[1]


def login(guest, version, selected, pid, arguments):
    output = guest.command("@{ home=/tmp/cpu-login; rc -el -c 'cpu-choice; "
                           "cat /cfg/nix9/files/version; echo $nix9System; "
                           f"echo $nix9WebfsSystem; hget {base}/payload' }}")
    for expected in ("CPU-LOGIN-PROFILE", version, selected, "CPU-HTTP-PAYLOAD"):
        if expected not in output.splitlines():
            raise RuntimeError(f"fresh login missing {expected}: {output}")
    if output.splitlines().count(version) != 2 or output.splitlines().count(selected) != 2:
        raise RuntimeError(f"login did not activate packages, files and webfs: {output}")
    if clock(guest, arguments) != pid:
        raise RuntimeError("login replaced the running clock")


def startup(guest, version, selected, address, arguments):
    guest.command(f"cat {SYSTEM}-boot", selected)
    output = guest.command("cat /tmp/cpu-startup")
    for expected in ("cpu", "nix9-cpu", version, selected, address, "10.0.2.3",
                     "CPU-HTTP-PAYLOAD", "CPU-STARTUP-END"):
        if expected not in output.splitlines():
            raise RuntimeError(f"CPU boot namespace missing {expected}: {output}")
    if output.splitlines().count(version) != 2 or output.splitlines().count(selected) != 2:
        raise RuntimeError(f"CPU boot did not activate packages, files and webfs: {output}")
    guest.command("test -A /sys/log/nix9 && test -A /sys/log/timesync")
    events = guest.command("cat /sys/log/nix9")
    if not any(" boot " in line and selected in line for line in events.splitlines()):
        raise RuntimeError("CPU startup did not record its boot event")
    guest.command("cat /tmp/cpu-native-startup", "ORIGINAL-CPU-CONFIG")
    for path, original in ((CPU_HOOK + ".nix9-original", "/tmp/original-cpu-hook"),
                           ("/rc/bin/termrc.local.nix9-original", "/tmp/original-term-hook"),
                           ("/rc/lib/rcmain.local.nix9-original", "/tmp/original-login-hook"),
                           ("/rc/bin/cpurc", "/tmp/original-cpurc"),
                           ("/lib/ndb/local", "/tmp/original-ndb")):
        guest.command(f"cmp {path} {original}")
    # init's console rc is not a login shell. Activate this separate namespace
    # only after checking the namespace captured by native /cfg/.../cpustart.
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("echo `{cat /dev/sysname}", "nix9-cpu")
    guest.command("cpu-choice", version)
    pid = clock(guest, arguments)
    login(guest, version, selected, pid, arguments)
    return pid


def reject(guest, command, reason, selected):
    output = guest.command(command + "; echo CPU-ERROR:$status")
    if not re.search(r"(?m)^CPU-ERROR:.+", output) or reason not in output:
        raise RuntimeError(f"did not reject {reason}: {output}")
    if root(guest) != selected:
        raise RuntimeError("rejected operation changed the selection")
    guest.command("test ! -e '#s/nix9-system'")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_CPU_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "cpu.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("cpu.nix"), work / "cpu.nix")
    (work / "payload").write_text("CPU-HTTP-PAYLOAD\n")
    # Nvrsafe has byte arrays, each followed by (9 + sum(array)) modulo 256.
    # A hostowner and domain avoid interactive CPU boot prompts; all key bytes
    # remain zero. This fixture supplies no usable authentication credentials.
    fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
              b"nix9.test".ljust(48, b"\0"), bytes(16))
    (work / "nvram").write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
    ntp = stack.enter_context(socketserver.UDPServer(("127.0.0.1", 0), NTP))
    ntp.replied = threading.Event()
    (work / "cpu-fixture.nix").write_text("{ port = " + str(ntp.server_address[1]) + "; }\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    http = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
    for server in (ntp, http):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stack.callback(thread.join)
        stack.callback(server.shutdown)
    base = f"http://10.0.2.2:{http.server_port}"
    endpoint = f"udp!10.0.2.2!{ntp.server_address[1]}"
    rtc_args = ["-l", "-r"]
    ntp_args = ["-l", "-n", endpoint]
    native_args = ["-n", endpoint]
    (work / "original-cpu-hook").write_text(
        "echo ORIGINAL-CPU-HOOK >> /tmp/cpu-original-runs\n"
        f"ntp={endpoint}\nauth=cpu-auth.invalid\ncpuFixtureURL={base}\n")
    (work / "cpustart").write_text(
        "{\necho $service\necho `{cat /dev/sysname}\n"
        "echo $nix9System\ncpu-choice\ncat /cfg/nix9/files/version\n"
        "echo $nix9WebfsSystem\nndb/query -f /net/ndb sys nix9-cpu ip\n"
        "ndb/query -f /net/ndb sys nix9-cpu dns\n"
        "hget $cpuFixtureURL/payload\necho CPU-STARTUP-END\n} > /tmp/cpu-startup\n")
    with boot(qemu, disk, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        for name in ("cpu.nix", "cpu-fixture.nix", "nvram", "original-cpu-hook", "cpustart"):
            guest.command(f"hget -o /tmp/{name} {base}/{name}")
        for name in ("legacy", "one", "two", "unmanaged"):
            guest.command(f"echo '(import ./cpu.nix).{name}' > /tmp/{name}.nix")
        guest.command("cp /rc/bin/cpurc /tmp/original-cpurc; cp /lib/ndb/local /tmp/original-ndb")
        guest.command(f"cp /tmp/original-cpu-hook {CPU_HOOK}")
        guest.command("echo '# ORIGINAL-TERM-HOOK' >> /rc/bin/termrc.local")
        guest.command("echo '# ORIGINAL-LOGIN-HOOK' >> /rc/lib/rcmain.local")
        guest.command("cp /rc/bin/termrc.local /tmp/original-term-hook")
        guest.command("cp /rc/lib/rcmain.local /tmp/original-login-hook")
        guest.command("mkdir -p /tmp/cpu-login/lib /cfg/nix9-cpu/service")
        guest.command("echo 'echo CPU-LOGIN-PROFILE' > /tmp/cpu-login/lib/profile")
        guest.command("cp /tmp/cpustart /cfg/nix9-cpu/cpustart")
        guest.command("echo 'echo ORIGINAL-CPU-CONFIG > /tmp/cpu-native-startup' > /cfg/nix9-cpu/cpurc")
        # Record the actual arguments before the real native daemon discards
        # /proc/args during rfork; this is not a substitute timesync process.
        guest.command("mkdir -p /tmp/timesync-native; mv /$cputype/bin/aux/timesync /tmp/timesync-native/timesync")
        guest.command("echo '#!/bin/rc' > /$cputype/bin/aux/timesync")
        guest.command("echo 'echo timesync $* > /tmp/timesync-invocation' >> /$cputype/bin/aux/timesync")
        guest.command("echo 'exec /tmp/timesync-native/timesync $*' >> /$cputype/bin/aux/timesync")
        guest.command("chmod 755 /$cputype/bin/aux/timesync")
        # The first selection predates CPU templates: the new rebuild program
        # must install its runtime template while keeping the existing script.
        guest.command("nix9-rebuild switch /tmp/legacy.nix")
        legacy = root(guest)
        guest.command(f"test ! -f {legacy}/hooks/cpurc.local")
        guest.command(f"cmp {CPU_HOOK} $nix9/packages/system/cpurc.local")
        guest.command("nix9-rebuild switch /tmp/one.nix")
        one = root(guest)
        guest.command(f"cp {CPU_HOOK} /tmp/managed-cpu-hook")
        guest.command(f"echo '# edited' >> {CPU_HOOK}")
        reject(guest, "nix9-rebuild switch /tmp/legacy.nix", "startup hook was edited", one)
        guest.command(f"cp /tmp/managed-cpu-hook {CPU_HOOK}")
        guest.command(f"rm {CPU_HOOK}")
        reject(guest, "nix9-rebuild rollback", "startup hook was removed", one)
        guest.command(f"cp /tmp/managed-cpu-hook {CPU_HOOK}")
        guest.command(f"mv {CPU_HOOK}.nix9-original /tmp/cpu-hook-backup")
        reject(guest, "nix9-rebuild rollback", "startup backup is missing", one)
        guest.command(f"mv /tmp/cpu-hook-backup {CPU_HOOK}.nix9-original")
        guest.command("dd -if /tmp/nvram -of /dev/sdF0/nvram -bs 126 -count 1")
        guest.command("9fs 9fat")
        guest.command("echo 'service=cpu' >> /n/9fat/plan9.ini")
        guest.command("echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")
        print("PASS: legacy adoption, original hooks preserved and manual edits rejected", flush=True)
    options = dict(snapshot=False, configure_network=False, cpu=True, prompt=CPU_PROMPT)
    with boot(qemu, disk, **options) as guest:
        pid = startup(guest, "one", one, "10.0.2.15", rtc_args)
        guest.command("nix9-rebuild switch /tmp/two.nix")
        two = root(guest)
        login(guest, "two", two, pid, rtc_args)
        guest.command("for(i in 1 2 3) . /usr/local/pkg/nix9/system")
        guest.command("cpu-choice", "two")
        guest.command("ndb/query -f /net/ndb sys nix9-cpu ip", "10.0.2.15")
        if clock(guest, rtc_args) != pid or ntp.replied.is_set():
            raise RuntimeError("switch or refresh changed the boot clock")
        print("PASS: CPU boot environment, DHCP, RTC, webfs, logging and fresh login selection", flush=True)
    with boot(qemu, disk, **options) as guest:
        pid = startup(guest, "two", two, "10.0.2.42", ntp_args)
        if not ntp.replied.wait(5):
            raise RuntimeError("CPU clock did not contact the local NTP fixture")
        seconds = re.findall(r"(?m)^([0-9]{10})$", guest.command("date -n"))
        if len(seconds) != 1 or abs(int(seconds[0]) - time.time() - OFFSET) > 10:
            raise RuntimeError(f"CPU timesync did not correct the clock: {seconds}")
        corrections = guest.command("cat /sys/log/timesync")
        if not re.search(r"nix9-cpu .* δ -?[0-9]+ avgδ [0-9]+ hz [0-9]+", corrections):
            raise RuntimeError("CPU timesync did not log a clock correction")
        guest.command("nix9-rebuild rollback")
        if root(guest) != one:
            raise RuntimeError("CPU rollback selected the wrong generation")
        login(guest, "one", one, pid, ntp_args)
        guest.command("ndb/query -f /net/ndb sys nix9-cpu ip", "10.0.2.42")
        print("PASS: static CPU network, NTP clock correction and rollback without restarting services", flush=True)
    with boot(qemu, disk, **options) as guest:
        startup(guest, "one", one, "10.0.2.15", rtc_args)
        guest.command("nix9-rebuild switch /tmp/legacy.nix")
        if root(guest) != legacy:
            raise RuntimeError("legacy generation was not reused")
        print("PASS: reboot restores rolled-back network and RTC settings", flush=True)
    with boot(qemu, disk, **options) as guest:
        startup(guest, "legacy", legacy, "10.0.2.15", rtc_args)
        guest.command("nix9-rebuild switch /tmp/unmanaged.nix")
        unmanaged = root(guest)
        print("PASS: retained generation without a CPU template boots through the stable loader", flush=True)
    with boot(qemu, disk, **options) as guest:
        startup(guest, "unmanaged", unmanaged, "10.0.2.15", native_args)
        guest.command(f"test ! -f {unmanaged}/services/timesync.rc")
        guest.command("echo `{wc -l < /tmp/cpu-original-runs}", "5")
        print("PASS: unmanaged CPU timesync uses native startup and preserved site configuration", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "firstSystem": one, "secondSystem": two,
        "legacySystem": legacy, "unmanagedSystem": unmanaged, "configuredCpuBoots": 5,
        "checks": ["native-cpu-init", "boot-namespace", "preserved-local-hooks",
                   "native-machine-startup", "edited-hooks-rejected", "dhcp", "static-ipv4",
                   "managed-webfs", "logging", "rtc", "local-ntp-correction", "single-clock",
                   "fresh-login", "boot-only-changes", "rollback", "legacy-generation",
                   "native-unmanaged-clock"],
    }, indent=2) + "\n")
