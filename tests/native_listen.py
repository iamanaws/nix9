"""Connect to native CPU listeners across generation switches and reboots."""

from contextlib import ExitStack, nullcontext
import functools
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

from guest import boot


SYSTEM = "/usr/local/nix/state/gcroots/machines/test/system"
SERVICE = "/cfg/nix9-listen/service"
CPU_PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"
INVALID = {
    "invalidEnable": "enable", "invalidTCP": "tcp", "invalidZero": "tcp ports",
    "invalidHigh": "tcp ports", "invalidLeadingZero": "tcp ports", "invalidName": "tcp ports",
    "invalidOption": "tcp ports", "invalidScript": "tcp scripts",
    "invalidEmptyScript": "tcp scripts", "disabledScripts": "tcp requires",
}


def root(guest):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"cat {SYSTEM}"))
    if len(paths) != 1:
        raise RuntimeError(f"missing selected system: {paths}")
    return paths[0]


def reject(guest, command, reason, selected):
    output = guest.command(command + "; echo LISTEN-ERROR:$status")
    if not re.search(r"(?m)^LISTEN-ERROR:.+", output) or reason not in output:
        raise RuntimeError(f"did not reject {reason}: {output}")
    if root(guest) != selected:
        raise RuntimeError("rejected service configuration changed the selection")
    guest.command("test ! -e '#s/nix9-system-test'")


def connect(port):
    deadline = time.monotonic() + 15
    while True:
        try:
            connection = socket.create_connection(("127.0.0.1", port), timeout=3)
            connection.settimeout(10)
            return connection
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)


def response(connection):
    # The persistent fixture answers multiple requests on one connection.
    data = b""
    while not data.endswith(b"LISTEN-END\n"):
        chunk = connection.recv(4096)
        if not chunk:
            raise RuntimeError(f"service closed before its response: {data!r}")
        data += chunk
        if len(data) > 16384:
            raise RuntimeError("service response exceeded the fixture limit")
    return data.decode().replace("\r", "").splitlines()


def closed(connection):
    try:
        data = connection.recv(1)
    except TimeoutError as error:
        raise RuntimeError("a finished service retained its TCP connection") from error
    if data:
        raise RuntimeError(f"unexpected data after service completion: {data!r}")


def snapshot(connection, version, selected):
    connection.sendall(b"snapshot\n")
    lines = response(connection)
    if lines[:5] != [version, version, "none", selected, selected]:
        raise RuntimeError(f"wrong service user, packages, files or webfs namespace: {lines}")
    if not re.fullmatch(r"tcp17010 tcp /net/tcp/[0-9]+", lines[5]):
        raise RuntimeError(f"native connection arguments were lost: {lines}")
    if lines[6:] != ["LISTEN-HTTP-PAYLOAD", "LISTEN-END"]:
        raise RuntimeError(f"service could not fetch through managed webfs: {lines}")


def unavailable(guest, port, number):
    # Check kernel listener state as well: QEMU can accept the host-side socket
    # and reset it later when the guest has no listener.
    table = guest.command("netstat -n")
    if re.search(r"(?m)^tcp\s+[0-9]+\s+\S+\s+Listen\s+" + str(number) + r"\s", table):
        raise RuntimeError(f"removed service still listening on {number}: {table}")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
            connection.settimeout(2)
            connection.sendall(b"snapshot\n")
            data = connection.recv(1024)
            if data:
                raise RuntimeError(f"disabled service returned data: {data!r}")
    except OSError:
        pass


def listening(guest, number):
    # QEMU accepts host forwards before the asynchronous native listener has
    # announced its guest port. Wait for kernel state, not a host-side accept.
    deadline = time.monotonic() + 15
    while True:
        table = guest.command("netstat -n")
        if re.search(r"(?m)^tcp\s+[0-9]+\s+\S+\s+Listen\s+" + str(number) + r"\s", table):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"native listener did not announce port {number}: {table}")
        time.sleep(0.2)


def native(guest, selected, manual_port):
    guest.command(f"cat {SYSTEM}-boot", selected)
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("cmp /rc/bin/cpurc /tmp/original-cpurc")
    guest.command(f"cmp {SERVICE}/tcp17011 /tmp/manual-service")
    guest.command(f"cmp {SERVICE}/tcp17011.namespace /tmp/manual-namespace")
    guest.command(f"test ! -e {SERVICE}/tcp17010 && test ! -e {SERVICE}/tcp17012")
    listening(guest, 17011)
    with connect(manual_port) as connection:
        if response(connection) != ["MANUAL-SERVICE", "none", "MANUAL-NAMESPACE", "LISTEN-END"]:
            raise RuntimeError("manual service or its namespace changed")
    lines = [line for line in guest.command("ps -a").splitlines()
             if re.search(r"\blisten \[tcp \* " + re.escape(SERVICE) + r"\]\x00?$", line)]
    if len(lines) != 1 or lines[0].split()[0] != "none":
        raise RuntimeError(f"expected one native service-directory listener: {lines}")
    return lines[0].split()[1]


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_LISTEN_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "listen.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("listen.nix"), work / "listen.nix")
    (work / "payload").write_text("LISTEN-HTTP-PAYLOAD\n")
    fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
              b"nix9.test".ljust(48, b"\0"), bytes(16))
    (work / "nvram").write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
    (work / "manual-service").write_text(
        "#!/bin/rc\necho MANUAL-SERVICE\necho $user\ncat /lib/ndb/local\necho LISTEN-END\n")
    (work / "manual-namespace").write_text(
        "bind /cfg/nix9-listen/manual-marker /lib/ndb/local\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    http = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join)
    stack.callback(http.shutdown)
    (work / "listen-fixture.nix").write_text("{ port = " + str(http.server_port) + "; }\n")
    base = f"http://10.0.2.2:{http.server_port}"
    ports = []
    with ExitStack() as reservations:
        for number in (17010, 17011, 17012):
            reservation = reservations.enter_context(socket.socket())
            reservation.bind(("127.0.0.1", 0))
            ports.append((reservation.getsockname()[1], number))
    main_port, manual_port, extra_port = [port for port, _ in ports]
    with boot(qemu, disk, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix9-rebuild init test")
        for name in ("listen.nix", "listen-fixture.nix", "nvram", "manual-service", "manual-namespace"):
            guest.command(f"hget -o /tmp/{name} {base}/{name}")
        for name in ("one", "two", "disabled", "empty", "baseline", *INVALID):
            guest.command(f"echo '(import ./listen.nix).{name}' > /tmp/{name}.nix")
        guest.command(f"mkdir -p {SERVICE}")
        guest.command(f"cp /tmp/manual-service {SERVICE}/tcp17011; chmod 755 {SERVICE}/tcp17011")
        guest.command(f"cp /lib/namespace {SERVICE}/tcp17011.namespace")
        guest.command(f"cat /tmp/manual-namespace >> {SERVICE}/tcp17011.namespace")
        guest.command(f"cp {SERVICE}/tcp17011.namespace /tmp/manual-namespace")
        guest.command("echo MANUAL-NAMESPACE > /cfg/nix9-listen/manual-marker")
        guest.command("cp /rc/bin/cpurc /tmp/original-cpurc")
        guest.command("echo 'auth=cpu-auth.invalid' > /rc/bin/cpurc.local")
        # Start with the native service set before enabling managed listeners.
        guest.command("nix9-rebuild switch /tmp/baseline.nix")
        baseline = root(guest)
        guest.command("nix9-rebuild switch /tmp/one.nix", "TCP service changes take effect after CPU-server reboot.")
        one = root(guest)
        for name, reason in INVALID.items():
            reject(guest, f"nix9-rebuild switch /tmp/{name}.nix", "services.listen." + reason, one)
        guest.command(f"echo manual-conflict > {SERVICE}/tcp17010")
        reject(guest, "nix9-rebuild switch /tmp/two.nix", "manual service or namespace already owns tcp17010", one)
        guest.command(f"rm {SERVICE}/tcp17010; echo manual-conflict > {SERVICE}/tcp17010.namespace")
        reject(guest, "nix9-rebuild switch /tmp/two.nix", "manual service or namespace already owns tcp17010", one)
        guest.command(f"rm {SERVICE}/tcp17010.namespace")
        guest.command("test ! -f /usr/local/nix/state/gcroots/machines/test/system-boot")
        guest.command("dd -if /tmp/nvram -of /dev/sdF0/nvram -bs 126 -count 1")
        guest.command("9fs 9fat")
        guest.command("echo 'service=cpu' >> /n/9fat/plan9.ini")
        guest.command("echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")
        print("PASS: validation, manual conflicts and selection without changing native services", flush=True)
    options = dict(snapshot=False, configure_network=False, cpu=True, prompt=CPU_PROMPT,
                   forward_ports=ports)
    with boot(qemu, disk, **options) as guest:
        pid = native(guest, one, manual_port)
        with connect(main_port) as connection:
            snapshot(connection, "one", one)
            with connect(extra_port) as extra:
                if response(extra) != ["EXTRA-SERVICE", "LISTEN-END"]:
                    raise RuntimeError("second declared port did not start")
                closed(extra)
            guest.command("nix9-rebuild switch /tmp/two.nix")
            two = root(guest)
            guest.command("for(i in 1 2 3) . /usr/local/pkg/nix9/system")
            guest.command("listen-choice", "two")
            snapshot(connection, "one", one)
            with connect(main_port) as fresh:
                snapshot(fresh, "one", one)
            if native(guest, one, manual_port) != pid:
                raise RuntimeError("selection or refresh replaced the native listener")
            connection.sendall(b"quit\n")
            closed(connection)
        print("PASS: TCP activation as none, package/file/webfs namespaces and boot-only updates", flush=True)
        guest.command("mkdir -p /cfg/default/service")
        guest.command("cp /tmp/manual-service /cfg/default/service/tcp17011; chmod 755 /cfg/default/service/tcp17011")
        guest.command("cp /tmp/manual-namespace /cfg/default/service/tcp17011.namespace")
        guest.command("mv /cfg/nix9-listen/service /cfg/nix9-listen/service.saved")
        SERVICE = "/cfg/default/service"
    with boot(qemu, disk, **options) as guest:
        pid = native(guest, two, manual_port)
        with connect(main_port) as connection:
            snapshot(connection, "two", two)
            unavailable(guest, extra_port, 17012)
            guest.command("nix9-rebuild rollback")
            if root(guest) != one:
                raise RuntimeError("rollback selected the wrong service generation")
            snapshot(connection, "two", two)
            with connect(main_port) as fresh:
                snapshot(fresh, "two", two)
            if native(guest, two, manual_port) != pid:
                raise RuntimeError("rollback replaced the native listener")
            connection.sendall(b"quit\n")
            closed(connection)
        print("PASS: reboot changes scripts and removes a port; rollback preserves running connections", flush=True)
        guest.command("mv /cfg/nix9-listen/service.saved /cfg/nix9-listen/service")
        guest.command("rm -r /cfg/default/service")
        SERVICE = "/cfg/nix9-listen/service"
    with boot(qemu, disk, **options) as guest:
        native(guest, one, manual_port)
        with connect(main_port) as connection:
            snapshot(connection, "one", one)
            guest.command("nix9-rebuild switch /tmp/disabled.nix")
            disabled = root(guest)
            snapshot(connection, "one", one)
        with connect(extra_port) as extra:
            if response(extra) != ["EXTRA-SERVICE", "LISTEN-END"]:
                raise RuntimeError("rollback did not restore the removed service")
            closed(extra)
        print("PASS: reboot restores rollback; disabling management waits for reboot", flush=True)
    with boot(qemu, disk, **options) as guest:
        native(guest, disabled, manual_port)
        unavailable(guest, main_port, 17010)
        unavailable(guest, extra_port, 17012)
        guest.command("nix9-rebuild switch /tmp/baseline.nix")
        if root(guest) != baseline:
            raise RuntimeError("baseline generation was not reused")
        print("PASS: disabling services removes managed ports and retains manual services", flush=True)
    with boot(qemu, disk, **options) as guest:
        native(guest, baseline, manual_port)
        unavailable(guest, main_port, 17010)
        guest.command("nix9-rebuild switch /tmp/one.nix")
        guest.command(f"echo '#!/bin/rc' > {SERVICE}/tcp17010")
        guest.command(f"echo 'echo LATE-MANUAL; echo LISTEN-END' >> {SERVICE}/tcp17010")
        guest.command(f"chmod 755 {SERVICE}/tcp17010; cp {SERVICE}/tcp17010 /tmp/late-manual")
        print("PASS: a retained system generation boots with native services", flush=True)
    with boot(qemu, disk, **options) as guest:
        guest.command(f"cat {SYSTEM}-boot", one)
        guest.command(". /usr/local/pkg/nix9/system")
        listening(guest, 17010)
        with connect(main_port) as connection:
            if response(connection) != ["LATE-MANUAL", "LISTEN-END"]:
                raise RuntimeError("startup overwrote a manual service added after selection")
        with connect(manual_port) as connection:
            if response(connection) != ["MANUAL-SERVICE", "none", "MANUAL-NAMESPACE", "LISTEN-END"]:
                raise RuntimeError("startup conflict suppressed the other manual service")
        guest.command(f"cmp {SERVICE}/tcp17010 /tmp/late-manual")
        unavailable(guest, extra_port, 17012)
        guest.command(f"rm {SERVICE}/tcp17010")
        guest.command("nix9-rebuild switch /tmp/empty.nix")
        empty = root(guest)
        print("PASS: a conflict added after selection restores native startup without overwriting it", flush=True)
    with boot(qemu, disk, **options) as guest:
        native(guest, empty, manual_port)
        unavailable(guest, main_port, 17010)
        print("PASS: an empty declaration retains the native service set", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "firstSystem": one, "secondSystem": two,
        "disabledSystem": disabled, "baselineSystem": baseline, "emptySystem": empty,
        "configuredCpuBoots": 7, "rejectedConfigurations": list(INVALID),
        "checks": ["real-tcp-connections", "native-none-user", "generation-package-environment",
                   "generation-files", "managed-webfs", "native-arguments", "single-native-listener",
                   "manual-services-and-namespaces", "native-directory-fallback", "manual-conflicts-rejected", "late-conflict-fallback", "boot-only-updates",
                   "persistent-connections", "connection-eof", "removed-port", "rollback", "disable", "baseline", "empty"],
    }, indent=2) + "\n")
