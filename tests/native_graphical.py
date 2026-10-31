"""Edit shared files in a real Rio/Acme session and compile on another CPU."""

from contextlib import ExitStack, contextmanager, nullcontext
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

from pexpect.fdpexpect import fdspawn
from guest import Guest, SerialLog, boot


ROOTS = "/usr/local/nix/state/gcroots"
PROMPT = r"(?m)^(?:term% |% |[a-z0-9-]+# )"
NAMES = ("auth", "files", "build", "terminal")


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def paths(output):
    return re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", output)


def until(guest, command, seconds=30):
    deadline = time.monotonic() + seconds
    while True:
        output = guest.command(command + "; echo GRAPH-WAIT:$status")
        if re.search(r"(?m)^GRAPH-WAIT:$", output):
            return output
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out: {command}: {output}")
        time.sleep(0.2)


def failed(guest, command, reason):
    output = guest.command("rc -c " + quote(command) + "; echo GRAPH-ERROR:$status")
    if not re.search(r"(?m)^GRAPH-ERROR:.+", output) or reason not in output or "syntax error" in output:
        raise RuntimeError(f"unexpected failure: {command}: {output}")
    return output


def services(guest):
    return set(re.findall(r"(?m)^(?:rio\.glenda\.[0-9]+|acme\.glenda\.[0-9]+|nix9-plumb\.glenda\.[0-9]+)$",
                          guest.command("ls -p /srv")))


def editor_window(guest, filename):
    index = guest.command("cat /mnt/acme/index")
    for line in index.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[0].isdigit() and fields[5].split()[0].rsplit("/", 1)[-1] == filename:
            return fields[0]
    raise RuntimeError(f"missing editor window {filename}: {index}")


qemu, image, archive, output = sys.argv[1:]
state = os.environ.get("NIX9_GRAPHICAL_TEST_STATE")
with ExitStack() as stack:
    work = Path(stack.enter_context(nullcontext(state) if state else tempfile.TemporaryDirectory()))
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    work.chmod(0o700)
    (work / "bootstrap.tar").symlink_to(Path(archive).resolve())
    shutil.copyfile(Path(__file__).with_name("graphical.nix"), work / "graphical.nix")
    keys = {name: secrets.token_bytes(16) for name in ("files", "build", "glenda")}
    for name, key in keys.items():
        role = "client" if name == "glenda" else "server"
        for suffix, data in (("keys", f"key proto=dp9ik dom=nix9.workstation user={name} role={role} "
                              f"!hex={key.hex()} !password=______\n".encode()), ("aes", key)):
            file = work / (name + "." + suffix)
            file.write_bytes(data)
            file.chmod(0o600)
    for name in NAMES:
        fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
                  (b"nix9.workstation" if name == "auth" else b"bootstrap.invalid").ljust(48, b"\0"), secrets.token_bytes(16))
        file = work / (name + ".nvram")
        file.write_bytes(b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields))
        file.chmod(0o600)
    http = stack.enter_context(http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=work)))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join)
    stack.callback(http.shutdown)
    base = f"http://10.0.2.2:{http.server_port}"

    def download(guest, name, destination, private=False):
        if private:
            guest.command(f"echo -n > {destination}; chmod 600 {destination}")
        guest.command(f"hget -o {destination} {base}/{name}")

    peers, reservations = [], {}
    for address, port in (("10.0.2.100", 567), ("10.0.2.101", 17020), ("10.0.2.102", 17019),
                          ("10.0.2.103", 17022), ("10.0.2.103", 17023)):
        reservation = stack.enter_context(socket.socket())
        reservation.bind(("127.0.0.1", 0))
        host = reservation.getsockname()[1]
        peers.append((address, port, host))
        reservations[host] = reservation

    def disk(path, backing):
        if path.exists():
            raise RuntimeError(f"refusing to overwrite {path}")
        subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2", "-F", "qcow2",
                        "-b", str(Path(backing).resolve()), str(path)], check=True)

    foundation = work / "bootstrap.qcow2"
    disk(foundation, image)
    with boot(qemu, foundation, snapshot=False) as guest:
        guest.child.timeout = 1200
        guest.command(f"cd / && hget {base}/bootstrap.tar | tar x")
        guest.command(". /usr/local/pkg/nix9/activate")
        guest.command("nix-build '<nix9>' -A auth -A rcpu -A ndb -A rio -A plumber -A acme --out-link " + ROOTS + "/graph-tools")
    print("PASS: native graphical packages and their libraries build from source", flush=True)

    disks, systems, variants = {}, {}, {}
    for name in NAMES:
        disks[name] = work / (name + ".qcow2")
        disk(disks[name], foundation)
        with boot(qemu, disks[name], snapshot=False) as guest:
            guest.child.timeout = 900
            guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init " + name)
            download(guest, "graphical.nix", "/tmp/graphical.nix")
            download(guest, name + ".nvram", "/tmp/boot.nvram", private=True)
            guest.command("dd -if /tmp/boot.nvram -of /dev/sdF0/nvram -bs 126 -count 1")
            if name == "auth":
                guest.command("rm -f /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                for identity in keys:
                    download(guest, identity + ".aes", "/tmp/identity.aes", private=True)
                    guest.command(f"mkdir /mnt/keys/{identity}; cp /tmp/identity.aes /mnt/keys/{identity}/aeskey")
            if name in ("files", "build"):
                download(guest, name + ".keys", "/adm/" + ("files" if name == "files" else "cpu") + ".keys", private=True)
            if name == "files":
                guest.command("mkdir -p /usr/glenda/projects/hello; cp $nix9/packages/examples/workstation/project/* /usr/glenda/projects/hello/")
                guest.command("echo first > /usr/glenda/projects/hello/notes.txt; echo second >> /usr/glenda/projects/hello/notes.txt")
            if name == "terminal":
                download(guest, "glenda.keys", "/adm/terminal.keys", private=True)
                guest.command("echo 'cat /adm/terminal.keys > /mnt/factotum/ctl' > /rc/bin/termrc.local")
                for variant in ("first", "second", "disabled", "malformed", "missingDirectory", "missingFont"):
                    guest.command(f"echo '(import ./graphical.nix {{}}).{variant}.systems.terminal' > /tmp/{variant}.nix")
                    variants[variant] = paths(guest.command(f"nix-build /tmp/{variant}.nix --out-link {ROOTS}/graph-{variant}"))[0]
                systems[name] = variants["first"]
                guest.command("nix9-rebuild select " + systems[name])
            else:
                guest.command(f"mkdir -p /cfg/{name}/service")
                guest.command(f"echo '(import ./graphical.nix {{}}).first.systems.{name}' > /tmp/system.nix")
                guest.command("nix9-rebuild switch /tmp/system.nix")
                systems[name] = paths(guest.command(f"cat {ROOTS}/machines/{name}/system"))[0]
                guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")

    @contextmanager
    def start(name):
        address = "10.0.2." + str(100 + NAMES.index(name))
        forwards = [(host, port) for peer, port, host in peers if peer == address]
        for host, _ in forwards:
            reservations[host].close()
        qmp_path = str(work.resolve() / "terminal.qmp")
        options = ["-qmp", f"unix:{qmp_path},server=on,wait=off"] if name == "terminal" else []
        with boot(qemu, disks[name], snapshot=False, configure_network=False, cpu=name != "terminal", prompt=PROMPT,
                  forward_ports=forwards, guest_forwards=peers[:-2], qemu_options=options) as guest:
            guest.child.timeout = 120
            guest.command(". /usr/local/pkg/nix9/system")
            if name != "terminal":
                port = {"auth": 567, "files": 17020, "build": 17019}[name]
                until(guest, "netstat -n | grep 'Listen *" + str(port) + " '")
            yield guest

    auth = stack.enter_context(start("auth"))
    files = stack.enter_context(start("files"))
    build = stack.enter_context(start("build"))
    terminal = stack.enter_context(start("terminal"))
    failed(terminal, "nix9-session", "graphics and mouse devices are required")
    terminal.command("monitor=vesa vgasize=1024x768x32 screenrc")
    terminal.command("test -e /dev/draw/new && test -e /dev/mouse")
    # Rio owns the serial keyboard. A one-shot test console keeps automation separate.
    terminal.command("@{ rfork ne; exec aux/listen1 -1 -t tcp!*!17022 rc -c "
                     + quote("prompt=('graph% ' '    '); exec rc -i >[2=1]") + " } &")
    until(terminal, "netstat -n | grep 'Listen *17022 '")
    host = peers[-2][2]
    connection = socket.create_connection(("127.0.0.1", host), timeout=30)
    child = fdspawn(connection.detach(), encoding="utf-8", timeout=120)
    child.logfile_read = SerialLog()
    stack.callback(child.close)
    child.expect(r"(?m)^graph% ")
    control = Guest(child, r"(?m)^graph% ")
    baseline = services(control)
    stock_plumbers = re.findall(r"(?m)^plumb\.glenda\.[0-9]+$", control.command("ls -p /srv"))

    def launch(expected_system, tabs):
        control.command("rm -f /tmp/window-system /tmp/window-tabs /tmp/window-directory /tmp/graph-build.status; nix9-session > /tmp/session.log >[2=1] &")
        try:
            until(control, "test -r /tmp/window-system && test -r /tmp/window-tabs && test -r /tmp/window-directory")
        except RuntimeError as error:
            raise RuntimeError("graphical startup failed: " + control.command("cat /tmp/session.log")) from error
        control.command("cat /tmp/window-system", expected_system)
        control.command("cat /tmp/window-tabs", str(tabs))
        control.command("cat /tmp/window-directory", "/n/projects/hello")
        until(control, "grep -s 'already running' /tmp/nested.log")
        control.command("test -s /tmp/nested.status")
        deadline = time.monotonic() + 15
        active = services(control) - baseline
        while len(active) < 3 and time.monotonic() < deadline:
            time.sleep(0.2)
            active = services(control) - baseline
        if len(active) != 3:
            screenshot("startup-failed.png")
            raise RuntimeError(f"expected one Rio, Acme and plumber: {active}: "
                               + control.command("cat /tmp/session.log; ls -p /srv; cat $nix9System/session/init; ps"))
        rio = next(item for item in active if item.startswith("rio."))
        acme = next(item for item in active if item.startswith("acme."))
        plumber = next(item for item in active if item.startswith("nix9-plumb."))
        control.command(f"mount /srv/{plumber} /mnt/plumb; mount /srv/{rio} /mnt/wsys none")
        return rio, acme, plumber

    def stop_session(active):
        control.command("unmount /mnt/plumb; unmount /mnt/wsys")
        control.command("echo hangup > /proc/" + active[0].rsplit(".", 1)[1] + "/note")
        for service in active:
            until(control, "test ! -e /srv/" + service)
        if services(control) != baseline:
            raise RuntimeError("graphical session leaked services")
        current = re.findall(r"(?m)^plumb\.glenda\.[0-9]+$", control.command("ls -p /srv"))
        if current != stock_plumbers:
            raise RuntimeError("managed session changed an existing native plumber")

    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)

    def screenshot(name):
        with socket.socket(socket.AF_UNIX) as channel:
            channel.connect(str(work.resolve() / "terminal.qmp"))
            stream = channel.makefile("rwb", buffering=0)
            stream.readline()
            for command in ({"execute": "qmp_capabilities"}, {"execute": "screendump", "arguments": {
                    "filename": str((destination / name).resolve()), "format": "png"}}):
                stream.write(json.dumps(command).encode() + b"\n")
                while True:
                    response = json.loads(stream.readline())
                    if "error" in response:
                        raise RuntimeError(response)
                    if "return" in response:
                        break

    active = launch(variants["first"], 4)
    screenshot("startup.png")
    # Execute a test command from Acme's tag, then use the editor's native files.
    # Acme exposes its 9P interface to its commands rather than posting it in /srv.
    def click(x, y, button):
        # Mouse button state belongs to the open file, including its release.
        control.command(f"{{ echo -n 'A {x} {y} {button}'; sleep 0.1; echo -n 'A {x} {y} 0' }} > /dev/mousein")
        time.sleep(0.1)

    control.command("test -x /bin/Graphctl")
    # Rio consumes the first left click when transferring keyboard focus.
    click(29, 20, 1)
    click(29, 20, 1)
    for character in "Graphctl ":
        control.command("echo -n " + quote(character) + " > /dev/kbdin")
        time.sleep(0.04)
    screenshot("tag.png")
    click(55, 20, 2)
    screenshot("tag-command.png")
    until(control, "netstat -n | grep 'Listen *17023 '")
    editor_socket = socket.create_connection(("127.0.0.1", peers[-1][2]), timeout=30)
    editor_child = fdspawn(editor_socket.detach(), encoding="utf-8", timeout=120)
    editor_child.logfile_read = SerialLog()
    editor_child.expect(r"(?m)^acme% ")
    editor_control = Guest(editor_child, r"(?m)^acme% ")
    editor_control.command("/bin/nix-build --version")
    failed(editor_control, "/bin/nix9-session", "already running")
    until(editor_control, "grep -s 'hello[.]c' /mnt/acme/index")
    editor = editor_window(editor_control, "hello.c")
    editor_control.command("echo -n '/shared workspace/' > /mnt/acme/" + editor + "/addr")
    editor_control.command("echo -n 'graphical workstation' > /mnt/acme/" + editor + "/data; echo put > /mnt/acme/" + editor + "/ctl")
    files.command("grep -s 'graphical workstation' /usr/glenda/projects/hello/hello.c")
    control.command("@{ rfork e; echo ready > /tmp/plumb-ready; dd -of /tmp/plumb-message -bs 8192 -count 1 } < /mnt/plumb/edit &")
    until(control, "test -r /tmp/plumb-ready")
    control.command("plumb /n/projects/hello/notes.txt:2")
    until(control, "test -s /tmp/plumb-message")
    message = control.command("cat /tmp/plumb-message; echo")
    if "addr=2" not in message:
        raise RuntimeError("plumbing lost the requested line address: " + message)
    until(editor_control, "grep -s 'notes[.]txt' /mnt/acme/index")
    note_id = editor_window(editor_control, "notes.txt")
    # Opening addr resets it. Hold a handle while copying and reading the dot.
    until(editor_control, "{ echo 'addr=dot' > /mnt/acme/" + note_id
          + "/ctl; echo `{cat /mnt/acme/" + note_id + "/addr} } <[3] /mnt/acme/"
          + note_id + "/addr | grep '^6 13$'")
    editor_child.close()
    control.command("echo build > /tmp/build-now")
    until(control, "test -r /tmp/graph-build.status", seconds=120)
    build_status = control.command("echo `{cat /tmp/graph-build.status}").strip()
    log = control.command("cat /tmp/graph-build.log")
    if build_status:
        raise RuntimeError(f"graphical build failed: {build_status}: {log}")
    result = paths(log)[0]
    if " on 'cpu://" not in log:
        raise RuntimeError("graphical shell did not dispatch to a CPU builder: " + log)
    control.command(result + "/bin/hello", "hello from the graphical workstation")
    control.command("cat " + result + "/builder", "build")
    build.command("nix-store --verify-path " + result)
    print("PASS: Acme edits shared storage, plumbing opens file addresses, graphical shell builds remotely", flush=True)

    screenshot("workstation.png")

    control.command(". /usr/local/pkg/nix9/system; . /usr/local/pkg/nix9/system")
    if services(control) - baseline != set(active):
        raise RuntimeError("refresh duplicated a graphical session")
    control.command("nix9-rebuild select " + variants["second"])
    control.command("cat /tmp/window-tabs", "4")
    stop_session(active)
    active = launch(variants["second"], 8)
    control.command("nix9-rebuild rollback")
    control.command("cat /tmp/window-tabs", "8")
    stop_session(active)
    stop_session(launch(variants["first"], 4))
    for variant, reason in (("malformed", "parse error"), ("missingDirectory", "working directory is unavailable"),
                            ("missingFont", "configured font is unavailable"), ("disabled", "session.enable")):
        control.command("nix9-rebuild select " + variants[variant])
        failed(control, "nix9-session", reason)
        until(control, "test ! -e /srv/" + active[2])
        if services(control) != baseline:
            raise RuntimeError(f"failed {variant} startup leaked services")
    control.command("nix9-rebuild select " + variants["first"])
    print("PASS: private lifecycle, nested-start rejection, refresh, generation changes, rollback and startup failures", flush=True)
    (destination / "results.json").write_text(json.dumps({"status": "passed", "machines": 4,
        "systems": systems, "remoteOutput": result, "editedFile": "/n/projects/hello/hello.c"}, indent=2) + "\n")
