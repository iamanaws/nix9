"""Activate private webfs mounts, change TLS pins and fetch after boot/login."""

from contextlib import ExitStack, nullcontext
import base64
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading

from guest import boot
from tls import certificate_pin
from webfs_tls import certificate


SYSTEM = "/usr/local/nix/state/gcroots/system"
DIGEST = "sha256-" + base64.b64encode(hashlib.sha256(b"42\n").digest()).decode()


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.requests.append(self.path)
        super().do_GET()


def identity(guest, path="/mnt/web"):
    result = guest.command(f"ls -ld {path} | awk '{{print $2 \":\" $3}}'")
    ids = re.findall(r"(?m)^M:[0-9]+$", result)
    if len(ids) != 1:
        raise RuntimeError(f"missing mount identity: {result}")
    return ids[0]


def root(guest):
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"cat {SYSTEM}"))
    if len(paths) != 1:
        raise RuntimeError(f"missing selected system: {paths}")
    return paths[0]


def reject(guest, command, reason):
    result = guest.command(command + "; echo SERVICE-ERROR:$status")
    if not re.search(r"(?m)^SERVICE-ERROR:.+", result) or reason not in result:
        raise RuntimeError(f"operation did not reject {reason}: {result}")


def fetch(guest, base, label):
    # hget without -o always transfers the response body.
    guest.command(f"hget {base}/payload?{label}", "42")


def nix_fetch(guest, base, label):
    expression = ('builtins.fetchurl { url="' + base + '/payload?' + label
                  + '"; name="services-' + label + '"; sha256="' + DIGEST + '"; }')
    result = guest.command(f"nix-instantiate --eval --expr '{expression}'")
    if not re.search(r'"/usr/local/nix/store/[^"\n]+"', result):
        raise RuntimeError(f"Nix fetch did not return a store path: {result}")


def selected(guest):
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("echo $nix9WebfsSystem", root(guest))
    current = identity(guest)
    if current != identity(guest, "/mnt/nix9-webfs"):
        raise RuntimeError("webfs is not using the managed overlay")
    return current


def login(guest, base, label):
    previous = identity(guest)
    result = guest.command(f"@{{ home=/tmp/service-login; rc -el -c 'hget {base}/payload?{label}' }}", "42")
    if "SERVICE-LOGIN-PROFILE" not in result:
        raise RuntimeError(f"login profile was skipped: {result}")
    if identity(guest) != previous:
        raise RuntimeError("login changed the parent namespace")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_SERVICES_TEST_STATE")
with ExitStack() as stack:
    directory = stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory())
    work = Path(directory)
    work.mkdir(parents=True, exist_ok=True)
    disk = work / "services.qcow2"
    if disk.exists():
        raise RuntimeError(f"refusing to overwrite an existing test VM: {disk}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    for name in ("services.nix", "services-legacy.rc", "services-retained.rc"):
        shutil.copyfile(Path(__file__).with_name(name), work / name)
    (work / "payload").write_text("42\n")
    pairs = [certificate(work, name) for name in ("one", "two")]
    pins = [certificate_pin(cert).split("=", 1)[1] for cert, _ in pairs]
    (work / "service-pins.nix").write_text('{ one = "' + pins[0] + '"; two = "' + pins[1] + '"; }\n')
    # A headless terminal profile retains the activated boot namespace and models
    # glenda's bare webfs invocation without starting rio on a display-less VM.
    (work / "terminal-profile.rc").write_text("webfs\nprompt=('term% ' '\t')\nexec rc -i\n")
    (work / "login-profile.rc").write_text("webfs\necho SERVICE-LOGIN-PROFILE\n")
    servers = []
    for pair in (None, *pairs):
        handler = functools.partial(Handler, directory=work)
        server = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
        server.requests = []
        if pair:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(*pair)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        stack.callback(thread.join)
        stack.callback(server.shutdown)
        servers.append(server)
    plain, secure_one, secure_two = servers
    http_url = f"http://10.0.2.2:{plain.server_port}"
    first_url = f"https://10.0.2.2:{secure_one.server_port}"
    second_url = f"https://10.0.2.2:{secure_two.server_port}"
    with boot(qemu, disk, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command(f"cd / && hget {http_url}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        for name in ("services.nix", "services-legacy.rc", "services-retained.rc", "service-pins.nix",
                     "terminal-profile.rc", "login-profile.rc"):
            guest.command(f"hget -o /tmp/{name} {http_url}/{name}")
        for name in ("one", "two", "disabled", "invalid", "legacy"):
            guest.command(f"echo '(import ./services.nix).{name}' > /tmp/{name}.nix")
        manual = identity(guest)
        reject(guest, "nix9-rebuild switch /tmp/invalid.nix", "services.webfs.enable")
        guest.command("fn webfs { status='' }")
        reject(guest, "nix9-rebuild switch /tmp/one.nix", "existing rc function")
        guest.command(f"test ! -e {SYSTEM}; fn webfs")
        guest.command("nix9-rebuild switch /tmp/one.nix")
        one = root(guest)
        if identity(guest) != manual:
            raise RuntimeError("rebuild preflight changed the caller's service")
        original = selected(guest)
        fetch(guest, http_url, "initial-http")
        fetch(guest, first_url, "initial-https")
        nix_fetch(guest, first_url, "initial-nix")
        guest.command("for(i in 1 2 3 4 5) { . /usr/local/pkg/nix9/system; webfs }")
        if identity(guest) != original:
            raise RuntimeError("repeated activation or bare startup replaced the service")
        guest.command("savedRuntime=$nix9; mkdir -p /tmp/service-runtime/bin")
        guest.command("bind $nix9/bin /tmp/service-runtime/bin")
        guest.command("nix9=/tmp/service-runtime; . $nix9System/activate")
        if identity(guest) == original:
            raise RuntimeError("a different runtime reused the previous server")
        fetch(guest, first_url, "runtime-change")
        original = selected(guest)
        guest.command("$nix9/bin/webfs -m /mnt/replaced-webfs")
        guest.command("bind -b /mnt/replaced-webfs /mnt/web")
        reject(guest, ". /usr/local/pkg/nix9/system", "managed overlay")
        guest.command("nix9-rebuild switch /tmp/legacy.nix")
        reject(guest, ". /usr/local/pkg/nix9/system", "managed overlay")
        guest.command("~ $#nix9WebfsStop 0")
        guest.command("unmount /mnt/replaced-webfs /mnt/web; unmount /mnt/replaced-webfs")
        guest.command("nix9-rebuild switch /tmp/one.nix; nix9-rebuild delete 2")
        if selected(guest) != original:
            raise RuntimeError("an edited overlay replaced the managed server")
        guest.command("mkdir -p /tmp/service-login/lib")
        guest.command("cp /tmp/login-profile.rc /tmp/service-login/lib/profile")
        login(guest, first_url, "initial-login")
        guest.command(f"serviceOldURL={first_url}/payload?retained")
        guest.command("rc /tmp/services-retained.rc &")
        guest.command("while(! test -f /tmp/retained-ready) sleep 1; status=''")
        guest.command("nix9-rebuild switch /tmp/two.nix")
        two = root(guest)
        updated = selected(guest)
        if updated == original:
            raise RuntimeError("a new generation reused the previous policy namespace")
        before = len(secure_one.requests)
        reject(guest, f"hget {first_url}/payload?changed-pin", "not trusted")
        if len(secure_one.requests) != before:
            raise RuntimeError("a changed pin allowed an HTTP request")
        fetch(guest, second_url, "changed-pin")
        nix_fetch(guest, second_url, "changed-nix")
        guest.command("echo go > /tmp/retained-go")
        guest.command("while(! test -f /tmp/retained-status) sleep 1; status=''")
        guest.command("cat /tmp/retained-status", "passed")
        guest.command("cat /tmp/retained-output", "42")
        guest.command("nix9-rebuild rollback")
        if root(guest) != one:
            raise RuntimeError("rollback selected the wrong generation")
        selected(guest)
        fetch(guest, first_url, "rollback")
        reject(guest, f"hget {second_url}/payload?rollback-reject", "not trusted")
        guest.command("nix9-rebuild switch /tmp/disabled.nix")
        guest.command(". /usr/local/pkg/nix9/system")
        if identity(guest) != manual:
            raise RuntimeError("disabling webfs did not restore the manual mount")
        guest.command("test ! -e /mnt/nix9-webfs/clone; ~ $#nix9WebfsSystem 0")
        guest.command("nix9-rebuild switch /tmp/two.nix")
        selected(guest)
        guest.command("nix9-rebuild switch /tmp/legacy.nix")
        guest.command(". /usr/local/pkg/nix9/system")
        if identity(guest) != manual:
            raise RuntimeError("legacy activation retained a managed TLS namespace")
        guest.command("~ $#nix9WebfsSystem 0")
        guest.command("nix9-rebuild switch /tmp/two.nix")
        selected(guest)
        guest.command("cp /usr/glenda/lib/profile /tmp/original-profile")
        guest.command("cp /tmp/terminal-profile.rc /usr/glenda/lib/profile")
        print("PASS: activation, idempotence, TLS changes, isolated sessions, disable and legacy selection", flush=True)
    options = dict(snapshot=False, configure_network=False)
    with boot(qemu, disk, **options) as guest:
        guest.command("echo $nix9WebfsSystem", two)
        fetch(guest, http_url, "boot-http")
        fetch(guest, second_url, "boot-https")
        nix_fetch(guest, second_url, "boot-nix")
        login(guest, second_url, "boot-login")
        guest.command("nix9-rebuild rollback")
        # The previous retained generation is the first configuration.
        if root(guest) != one:
            raise RuntimeError("reboot rollback selected the wrong generation")
        selected(guest)
        fetch(guest, first_url, "boot-rollback")
        print("PASS: HTTP/HTTPS and Nix fetches after boot and login without manual service setup", flush=True)
    with boot(qemu, disk, **options) as guest:
        guest.command("echo $nix9WebfsSystem", one)
        fetch(guest, first_url, "rollback-reboot")
        reject(guest, f"hget {second_url}/payload?rollback-reboot-reject", "not trusted")
        print("PASS: reboot uses the rolled-back TLS policy", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "firstSystem": one, "secondSystem": two,
        "checks": ["automatic-boot-and-login", "http-and-https", "nix-fetchurl",
                   "idempotent-activation", "changed-pins", "isolated-sessions", "rollback",
                   "manual-mount-restored", "legacy-generation", "invalid-configuration",
                   "runtime-change", "edited-mount-rejected"],
    }, indent=2) + "\n")
