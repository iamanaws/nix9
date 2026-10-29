"""Authenticate through native rcpu and build client sources on a CPU server."""

from contextlib import ExitStack, nullcontext
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
SYSTEM = ROOTS + "/machines/test/system"
SERVICE = "/cfg/nix9-rcpu/service"
CPU_PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"
PINS = {"one": "a" * 64, "two": "b" * 64}


def store_root(guest, path=SYSTEM):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"cat {path}"))
    if len(paths) != 1:
        raise RuntimeError(f"missing store root at {path}: {paths}")
    return paths[0]


def secret_file(work, name, data):
    path = work / name
    path.write_bytes(data)
    path.chmod(0o600)


def private_download(guest, base, name):
    guest.command(f"echo -n > /tmp/{name}; chmod 600 /tmp/{name}")
    guest.command(f"hget -o /tmp/{name} {base}/{name}")


def snapshots(output):
    return [block.splitlines() for block in
            re.findall(r"(?ms)^RCPU-BEGIN\n(.*?)^RCPU-END\n", output)]


def check_snapshot(output, version, selected):
    expected = ["glenda", "nix9-rcpu", "cpu", version, version, selected, selected,
                "x509 sha256=" + PINS[version], "RCPU-HTTP-PAYLOAD"]
    records = snapshots(output)
    if len(records) != 1 or records[0] != expected:
        raise RuntimeError(f"wrong authenticated login namespace: {records}")
    if "not in union" in output or "activation failed" in output:
        raise RuntimeError(f"remote activation reported an error: {output}")


def login(client, version, selected):
    check_snapshot(client.command("remote -c rcpu-snapshot"), version, selected)


def persistent_snapshot(client, count, version, selected):
    client.command("echo snapshot > /mnt/rcpu-test/data")
    deadline = time.monotonic() + 30
    while True:
        output = client.command("cat /tmp/rcpu-session.out")
        records = snapshots(output)
        if len(records) == count:
            check_snapshot("RCPU-BEGIN\n" + "\n".join(records[-1]) + "\nRCPU-END\n",
                           version, selected)
            return
        if len(records) > count or time.monotonic() >= deadline:
            raise RuntimeError(f"persistent rcpu session did not answer: {output}")
        time.sleep(0.2)


def load_key(client, name):
    client.command("if(grep -s 'proto=dp9ik' /mnt/factotum/ctl) "
                   "echo 'delkey proto=dp9ik' > /mnt/factotum/ctl; if not status=''")
    if name:
        client.command(f"cat /tmp/{name} > /mnt/factotum/ctl")


def rejected_login(client, server):
    # Reject an interactive replacement-key prompt as EOF. Authentication and
    # TLS still use the unmodified native client, factotum and server.
    output = client.command("@{ rfork n; bind /dev/null /dev/cons; "
                            "bind /dev/null /dev/consctl; "
                            "remote -c 'echo BAD-LOGIN > /tmp/rcpu-rejected' }; "
                            "echo RCPU-ERROR:$status")
    if not re.search(r"(?m)^RCPU-ERROR:.+", output):
        raise RuntimeError(f"unauthorized rcpu login succeeded: {output}")
    server.command("test ! -e /tmp/rcpu-rejected")


def startup(server, selected):
    server.command(f"cat {SYSTEM}-boot", selected)
    server.command(". /usr/local/pkg/nix9/system")
    server.command(f"cmp {SERVICE}/tcp17019 /tmp/original-rcpu-service")
    server.command("cmp /rc/bin/cpurc /tmp/original-cpurc")
    server.command("test -A /sys/log/auth")
    for number in (567, 17019, 17010):
        deadline = time.monotonic() + 15
        while True:
            table = server.command("netstat -n")
            if re.search(r"(?m)^tcp\s+[0-9]+\s+\S+\s+Listen\s+" + str(number) + r"\s", table):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"CPU service did not announce port {number}: {table}")
            time.sleep(0.2)


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_RCPU_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    disk = work / "rcpu.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("rcpu.nix"), work / "rcpu.nix")
    shutil.copytree(Path(__file__).with_name("rcpu-project"), work / "rcpu-project")
    (work / "payload").write_text("RCPU-HTTP-PAYLOAD\n")

    # Generate credentials at test runtime, outside every derivation and result.
    # Different server/client IDs force a real authsrv ticket exchange rather
    # than factotum's shared-host-key fallback.
    # Match NVRAM's format: !password is a selection marker; !hex is the AES key.
    host_key, user_key = secrets.token_bytes(16), secrets.token_bytes(16)
    for name, user, role, key in (
        ("server.keys", "rcpuhost", "server", host_key),
        ("client.keys", "glenda", "client", user_key),
        ("bad.keys", "glenda", "client", secrets.token_bytes(16)),
    ):
        secret_file(work, name,
                    f"key proto=dp9ik dom=nix9.test user={user} role={role} "
                    f"!hex={key.hex()} !password=______\n".encode())
    secret_file(work, "server.aes", host_key)
    secret_file(work, "user.aes", user_key)
    fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
              b"nix9.test".ljust(48, b"\0"), secrets.token_bytes(16))
    secret_file(work, "nvram",
                b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
    (work / "cpu-hook").write_text(
        "auth=nix9-rcpu\n"
        "echo 'delkey proto=dp9ik' > /mnt/factotum/ctl\n"
        "cat /adm/rcpu-host.keys > /mnt/factotum/ctl\n")
    (work / "rcpu-build.rc").write_text(
        "#!/bin/rc -e\n"
        f"nix-build /mnt/term/tmp/rcpu-project --out-link {ROOTS}/rcpu-build\n"
        f"result=`{{cat {ROOTS}/rcpu-build}}\n"
        "$result/bin/rcpu-hello\n"
        "nix-store --verify-path $result\n"
        "echo RCPU-BUILD-END\n")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)
    http = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join)
    stack.callback(http.shutdown)
    base = f"http://10.0.2.2:{http.server_port}"
    (work / "rcpu-fixture.nix").write_text("{ port = " + str(http.server_port) + "; }\n")
    ports = []
    with ExitStack() as reservations:
        for number in (17019, 567, 17010):
            reservation = reservations.enter_context(socket.socket())
            reservation.bind(("127.0.0.1", 0))
            ports.append((reservation.getsockname()[1], number))
    cpu_port, auth_port, script_port = [port for port, _ in ports]

    with boot(qemu, disk, snapshot=False) as server:
        server.child.timeout = 900
        server.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        server.command(". /usr/local/pkg/nix9/activate")
        server.command("nix9-rebuild init test")
        for name in ("rcpu.nix", "rcpu-fixture.nix", "cpu-hook"):
            server.command(f"hget -o /tmp/{name} {base}/{name}")
        for name in ("nvram", "server.keys", "server.aes", "user.aes"):
            private_download(server, base, name)
        server.command("dd -if /tmp/nvram -of /dev/sdF0/nvram -bs 126 -count 1")
        server.command("rm -f /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
        server.command("mkdir /mnt/keys/rcpuhost /mnt/keys/glenda")
        server.command("cp /tmp/server.aes /mnt/keys/rcpuhost/aeskey")
        server.command("cp /tmp/user.aes /mnt/keys/glenda/aeskey")
        server.command("cp /tmp/server.keys /adm/rcpu-host.keys; chmod 600 /adm/rcpu-host.keys")
        server.command("cp /tmp/cpu-hook /rc/bin/cpurc.local")
        server.command(f"mkdir -p {SERVICE}")
        server.command(f"cp /rc/bin/service/tcp17019 {SERVICE}/tcp17019")
        server.command(f"cp {SERVICE}/tcp17019 /tmp/original-rcpu-service")
        server.command("cp /rc/bin/cpurc /tmp/original-cpurc")
        for name in ("one", "two"):
            server.command(f"echo '(import ./rcpu.nix).{name}' > /tmp/{name}.nix")
        server.command("nix9-rebuild switch /tmp/one.nix")
        one = store_root(server)
        server.command("9fs 9fat")
        server.command("echo 'service=cpu' >> /n/9fat/plan9.ini")
        server.command("echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    client = stack.enter_context(boot(qemu, image))
    client.child.timeout = 300
    client.command("test ! -e /usr/local/nix/store")
    # Once cs is available, factotum uses NDB rather than its bootstrap -a flag.
    client.command(f"echo 'authdom=nix9.test auth=tcp!10.0.2.2!{auth_port}' >> /lib/ndb/local")
    client.command("echo refresh > /net/cs")
    client.command("auth/factotum -n")
    for name in ("client.keys", "bad.keys"):
        private_download(client, base, name)
    load_key(client, "client.keys")
    client.command("mkdir -p /tmp/rcpu-project")
    for name in ("default.nix", "hello.c", "mkfile"):
        client.command(f"hget -o /tmp/rcpu-project/{name} {base}/rcpu-project/{name}")
    client.command(f"hget -o /tmp/rcpu-build.rc {base}/rcpu-build.rc")
    client.command(f"fn remote {{ rcpu -h tcp!10.0.2.2!{cpu_port} $* }}")
    options = dict(snapshot=False, configure_network=False, cpu=True,
                   prompt=CPU_PROMPT, forward_ports=ports)
    with boot(qemu, disk, **options) as server:
        server.child.timeout = 900
        startup(server, one)
        try:
            login(client, "one", one)
        except Exception:
            server.command("cat /sys/log/auth; ps -a; netstat -n")
            raise
        records = server.command("cat /sys/log/auth")
        if not re.search(r"tr-ok glenda@glenda.* -> glenda@rcpuhost", records):
            raise RuntimeError("rcpu did not obtain a ticket from native authsrv")
        with socket.create_connection(("127.0.0.1", script_port), timeout=10) as connection:
            connection.settimeout(10)
            received = b""
            while chunk := connection.recv(4096):
                received += chunk
            if received != b"RCPU-LISTENER-COEXISTENCE\n":
                raise RuntimeError(f"managed listener changed native authentication: {received!r}")
        print("PASS: native dp9ik tickets, TLS, authenticated identity and generation namespace", flush=True)

        result = client.command("remote -c rc /mnt/term/tmp/rcpu-build.rc", "RCPU-BUILD-END")
        if "hello from authenticated rcpu" not in result or not re.search(
                r"building '[^']*-rcpu-hello\.drv'", result):
            raise RuntimeError(f"rcpu did not compile the client project on the server: {result}")
        built = store_root(server, ROOTS + "/rcpu-build")
        server.command(f"{built}/bin/rcpu-hello", "hello from authenticated rcpu")
        client.command("test ! -e /usr/local/nix/store")
        print("PASS: client source export, native C build and verified server output", flush=True)

        for key in ("bad.keys", None):
            load_key(client, key)
            rejected_login(client, server)
        load_key(client, "client.keys")
        login(client, "one", one)
        print("PASS: wrong and missing credentials reject command execution", flush=True)

        # Keep the pipe's writer open between requests, rather than sending EOF
        # whenever an individual echo command closes its descriptor.
        client.command("bind '#|' /mnt/rcpu-test; sleep 600 > /mnt/rcpu-test/data &")
        client.command("pipeholder=$apid")
        client.command("remote -c rcpu-session < /mnt/rcpu-test/data1 "
                       "> /tmp/rcpu-session.out >[2] /tmp/rcpu-session.err &")
        client.command("sessionpid=$apid")
        persistent_snapshot(client, 1, "one", one)
        server.command("nix9-rebuild switch /tmp/two.nix")
        two = store_root(server)
        login(client, "two", two)
        persistent_snapshot(client, 2, "one", one)
        server.command("nix9-rebuild rollback")
        if store_root(server) != one:
            raise RuntimeError("rollback selected the wrong system")
        login(client, "one", one)
        persistent_snapshot(client, 3, "one", one)
        server.command("nix9-rebuild switch /tmp/two.nix")
        if store_root(server) != two:
            raise RuntimeError("switch did not reuse the retained generation")
        client.command("echo quit > /mnt/rcpu-test/data; wait $sessionpid")
        client.command("echo kill > /proc/$pipeholder/note; wait $pipeholder; status=''")
        client.command("test ! -s /tmp/rcpu-session.err")
        print("PASS: fresh login selection, persistent namespace and rollback", flush=True)

    with boot(qemu, disk, **options) as server:
        server.child.timeout = 300
        startup(server, two)
        login(client, "two", two)
        server.command(f"{built}/bin/rcpu-hello", "hello from authenticated rcpu")
        print("PASS: CPU reboot restores native authentication and selected generation", flush=True)

    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "firstSystem": one, "secondSystem": two,
        "remoteBuild": built, "configuredCpuBoots": 2,
        "checks": ["native-rcpu", "dp9ik-authsrv-tickets", "tls", "authenticated-user",
                   "selected-generation", "generated-files", "certificate-pins", "managed-webfs",
                   "client-source-export", "native-c-build", "verified-output",
                   "wrong-credentials", "missing-credentials", "persistent-session",
                   "fresh-logins", "switch", "rollback", "cpu-reboot", "manual-service-preserved",
                   "managed-listener-coexistence", "runtime-only-test-credentials"],
    }, indent=2) + "\n")
