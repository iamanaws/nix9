"""Configure native terminal timesync and correct time against a local UDP fixture."""

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


SYSTEM = "/usr/local/nix/state/gcroots/machines/test/system"
INVALID = {
    "invalidEnable": "enable", "invalidSource": "source", "invalidSourceType": "source",
    "invalidLocalTime": "rtcLocalTime", "missingServer": "server",
    "invalidLogging": "logging", "disabledLogging": "logging",
    "invalidServerType": "server", "invalidServer": "server", "invalidIP": "server",
    "ambiguousIP": "server", "multicastIP": "server", "unspecifiedIP": "server",
    "invalidHostname": "server", "serverOption": "server", "serverPort": "server",
    "invalidPort": "port", "invalidHighPort": "port", "invalidPortType": "port",
    "ntpLocalTime": "rtcLocalTime", "rtcServer": "server", "rtcPort": "port",
}


def root(guest):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"cat {SYSTEM}"))
    if len(paths) != 1:
        raise RuntimeError(f"missing selected system: {paths}")
    return paths[0]


def process(guest, arguments):
    output = guest.command("ps -a")
    lines = [line for line in output.splitlines() if re.search(r"\btimesync(?:\s|$)", line)]
    if len(lines) != 1:
        raise RuntimeError(f"expected exactly one native timesync process: {lines}")
    if arguments is not None:
        guest.command("cat /tmp/timesync-invocation", "timesync " + " ".join(arguments))
    return lines[0].split()[1]


def refresh(guest, arguments, pid):
    guest.command("for(i in 1 2 3) . /usr/local/pkg/nix9/system")
    output = guest.command("@{ home=/tmp/clock-login; rc -el -c 'echo TIMESYNC-LOGIN' }", "TIMESYNC-LOGIN")
    if "CLOCK-LOGIN-PROFILE" not in output:
        raise RuntimeError("login skipped the profile")
    if process(guest, arguments) != pid:
        raise RuntimeError("session refresh or login replaced the running timesync")


def select(guest, name, arguments, pid):
    guest.command(f"nix9-rebuild switch /tmp/{name}.nix", "Clock synchronization changes take effect after reboot.")
    refresh(guest, arguments, pid)
    return root(guest)


def clock_records(guest):
    return re.findall(r"(?m)^nix9-clock .+$", guest.command("cat /sys/log/timesync"))


def retained_records(guest, history):
    # The current client may append another sample before the next reboot.
    if clock_records(guest)[:len(history)] != history:
        raise RuntimeError("clock log history was lost during rollback or reboot")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_TIMESYNC_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "timesync.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("timesync.nix"), work / "timesync.nix")
    ntp = stack.enter_context(socketserver.UDPServer(("127.0.0.1", 0), NTP))
    ntp.replied = threading.Event()
    (work / "timesync-server.nix").write_text("{ port = " + str(ntp.server_address[1]) + "; }\n")
    (work / "terminal-profile.rc").write_text("prompt=('term% ' '\t')\nexec rc -i\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    http = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
    for server in (ntp, http):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stack.callback(thread.join)
        stack.callback(server.shutdown)
    base = f"http://10.0.2.2:{http.server_port}"
    native = ["-rLa1000000"]
    utc_args = ["-r"]
    ntp_args = ["-l", "-n", f"udp!10.0.2.2!{ntp.server_address[1]}"]
    local_args = ["-r", "-L"]
    with boot(qemu, disk, snapshot=False) as guest:
        guest.child.timeout = 900
        original = process(guest, None)
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix9-rebuild init test")
        for name in ("timesync.nix", "timesync-server.nix", "terminal-profile.rc"):
            guest.command(f"hget -o /tmp/{name} {base}/{name}")
        for name in ("utc", "ntp", "local", "disabled", *INVALID):
            guest.command(f"echo '(import ./timesync.nix).{name}' > /tmp/{name}.nix")
        guest.command("mkdir -p /tmp/clock-login/lib")
        guest.command("echo 'echo CLOCK-LOGIN-PROFILE' > /tmp/clock-login/lib/profile")
        # The daemon's rfork does not retain /proc/args. Record the invocation,
        # then run the real image binary to check native startup and clock changes.
        guest.command("mkdir -p /tmp/timesync-native; mv /$cputype/bin/aux/timesync /tmp/timesync-native/timesync")
        guest.command("echo '#!/bin/rc' > /$cputype/bin/aux/timesync")
        guest.command("echo 'echo timesync $* > /tmp/timesync-invocation' >> /$cputype/bin/aux/timesync")
        guest.command("echo 'exec /tmp/timesync-native/timesync $*' >> /$cputype/bin/aux/timesync")
        guest.command("chmod 755 /$cputype/bin/aux/timesync")
        utc = select(guest, "utc", None, original)
        for name, reason in INVALID.items():
            result = guest.command(f"nix9-rebuild switch /tmp/{name}.nix; echo CLOCK-ERROR:$status")
            if not re.search(r"(?m)^CLOCK-ERROR:.+", result) or "services.timesync." + reason not in result:
                raise RuntimeError(f"invalid clock configuration was accepted: {name}: {result}")
            if root(guest) != utc or process(guest, None) != original:
                raise RuntimeError("invalid configuration changed the system or running service")
            guest.command("test ! -e '#s/nix9-system-test'")
        # Keep the activated boot namespace without relying on graphical startup.
        guest.command("cp /usr/glenda/lib/profile /tmp/original-profile")
        guest.command("cp /tmp/terminal-profile.rc /usr/glenda/lib/profile")
        print("PASS: configuration validation and selection without changing the running clock", flush=True)
    options = dict(snapshot=False, configure_network=False)
    with boot(qemu, disk, **options) as guest:
        guest.command(f"cat {SYSTEM}-boot", utc)
        pid = process(guest, utc_args)
        ntp_system = select(guest, "ntp", utc_args, pid)
        if ntp.replied.is_set():
            raise RuntimeError("NTP started before reboot")
        print("PASS: UTC RTC configuration and boot-only NTP selection", flush=True)
    with boot(qemu, disk, **options) as guest:
        guest.command(f"cat {SYSTEM}-boot", ntp_system)
        pid = process(guest, ntp_args)
        if not ntp.replied.wait(5):
            raise RuntimeError("managed timesync did not contact the local NTP fixture")
        seconds = re.findall(r"(?m)^([0-9]{10})$", guest.command("date -n"))
        if len(seconds) != 1 or abs(int(seconds[0]) - time.time() - OFFSET) > 10:
            raise RuntimeError(f"timesync did not correct the guest clock: {seconds}")
        guest.command("test -A /sys/log/timesync && test -A /sys/log/nix9")
        corrections = clock_records(guest)
        if not any(re.fullmatch(r"nix9-clock .* δ -?[0-9]+ avgδ [0-9]+ hz [0-9]+", line) for line in corrections):
            raise RuntimeError(f"timesync did not log its clock correction: {corrections}")
        local = select(guest, "local", ntp_args, pid)
        disabled = select(guest, "disabled", ntp_args, pid)
        guest.command("nix9-rebuild rollback", "Clock synchronization changes take effect after reboot.")
        if root(guest) != local:
            raise RuntimeError("rollback did not select the local RTC generation")
        refresh(guest, ntp_args, pid)
        print("PASS: NTP corrects the clock; switch, login and rollback preserve one running client", flush=True)
    with boot(qemu, disk, **options) as guest:
        guest.command(f"cat {SYSTEM}-boot", local)
        retained_records(guest, corrections)
        pid = process(guest, local_args)
        if select(guest, "disabled", local_args, pid) != disabled:
            raise RuntimeError("disabling timesync did not reuse the unmanaged generation")
        print("PASS: rollback restores local-time RTC settings after reboot", flush=True)
    with boot(qemu, disk, **options) as guest:
        guest.command(f"cat {SYSTEM}-boot", disabled)
        pid = process(guest, native)
        refresh(guest, native, pid)
        guest.command("test ! -f $nix9System/services/timesync.rc")
        retained_records(guest, corrections)
        print("PASS: disabling management restores native terminal startup", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "utcSystem": utc, "ntpSystem": ntp_system,
        "localSystem": local, "unmanagedSystem": disabled,
        "rejectedConfigurations": list(INVALID), "configuredBoots": 4,
        "checks": ["utc-rtc", "local-rtc", "local-ntp-clock-correction", "timesync-logging", "single-client",
                   "boot-only-changes", "login", "rollback", "native-startup-restored"],
    }, indent=2) + "\n")
