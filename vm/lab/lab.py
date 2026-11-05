"""Persistent four-machine 9front lab, with independent serial consoles."""

import argparse
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import fcntl
import json
import os
from pathlib import Path
import select
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import termios
import time
import tty

import pexpect

from ethernet import Ethernet
from guest import boot
from provision import ADDRESSES, CPUS, MACHINES, provision


PROMPT = r"(?m)^(?:[a-z0-9-]+[%#] |% )"


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


class Lab:
    def __init__(self, work, progress):
        self.work, self.progress = work, progress
        self.qemu = os.environ["NIX9_LAB_QEMU"]
        self.stack = ExitStack()
        self.network = Ethernet(MACHINES)
        self.stack.callback(self.network.close)
        self.sockets = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="nix9-lab-")))
        self.guests = {}

    @contextmanager
    def machine(self, name, *, disk=None, provisioning=False):
        options = []
        if name == "bootstrap":
            options += ["-drive", f"file={self.work / 'roots/bootstrap'},format=raw,readonly=on,if=virtio"]
        if name == "files":
            for volume in ("cache", "worm"):
                options += ["-drive", f"file={self.work / (volume + '.raw')},format=raw,if=virtio"]
        if not provisioning:
            options += ["-serial", f"unix:{self.sockets / name},server=on,wait=off"]
        backend = "user" if provisioning else self.network.backend(
            name, f"52:54:00:12:34:{MACHINES.index(name):02x}")
        with boot(self.qemu, disk or self.work / (name + ".qcow2"), snapshot=False,
                  cpu=not provisioning, configure_network=provisioning, prompt=PROMPT,
                  boot_prompt=provisioning or name in ("auth", "files"),
                  network_backend=backend, qemu_options=options) as guest:
            guest.child.timeout = 1200
            try:
                yield guest
            finally:
                if guest.child.isalive() and not guest.crashed:
                    self.progress(f"Halting {name}...")
                    guest.child.timeout = 120
                    guest.child.send("\x7f")
                    guest.child.expect(PROMPT, timeout=30)
                    guest.child.sendline("fshalt")
                    guest.child.expect("done halting")
                    guest.crash()

    def start(self, name):
        self.progress(f"Starting {name}...")
        guest = self.stack.enter_context(self.machine(name))
        self.guests[name] = guest
        guest.command(". /usr/local/pkg/nix9/system")
        ports = (567,) if name == "auth" else (564,) if name == "files" else (17019, 17051)
        for port in ports:
            deadline = time.monotonic() + 90
            while "LAB-READY" not in guest.command(
                    f"if(netstat -n | grep -s 'Listen *{port} ') echo LAB-READY; status=''"):
                if time.monotonic() > deadline:
                    raise RuntimeError(f"{name}: service on port {port} did not start")
                time.sleep(0.2)
        if name == "auth":
            for user in ("glenda", "alice", "bob"):
                guest.command(f"cat /adm/{user}.keys > /mnt/factotum/ctl")
        return guest

    def consoles(self):
        for guest in self.guests.values():
            guest.command("bind -a '#t' /dev; test -e /dev/eia1")
            guest.command("echo b115200 > /dev/eia1ctl")
            # The native console simulator supplies editing, /dev/consctl and notes.
            # It runs over the private UART, without opening a network listener.
            guest.command("@{ rfork n; while() { @{ rfork s; exec /bin/ip/telnetd -tn "
                          "</dev/eia1 >/dev/eia1 >[2=1] } } } &")

    def close(self):
        self.stack.close()


def console(work, machine):
    if not (work / "run.json").exists():
        raise RuntimeError("the lab is stopped")
    running = json.loads((work / "run.json").read_text())
    if running["phase"] != "ready":
        raise RuntimeError("the lab is still starting")
    with socket.socket(socket.AF_UNIX) as connection:
        connection.connect(running["consoles"][machine])
        print("Connected. Press Enter for a prompt; Ctrl-] detaches.", flush=True)
        previous = termios.tcgetattr(sys.stdin) if sys.stdin.isatty() else None
        try:
            if previous:
                tty.setraw(sys.stdin.fileno())
            while True:
                readable, _, _ = select.select([connection, sys.stdin], [], [])
                if connection in readable:
                    data = connection.recv(65536)
                    if not data:
                        break
                    os.write(sys.stdout.fileno(), data)
                if sys.stdin in readable:
                    data = os.read(sys.stdin.fileno(), 4096)
                    if not data or b"\x1d" in data:
                        break
                    # Translate the host terminal's erase/interrupt keys to Plan 9.
                    connection.sendall(data.replace(b"\x7f", b"\x08").replace(b"\x03", b"\x7f"))
        finally:
            if previous:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, previous)


def run(work):
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work.stat().st_uid != os.getuid():
        raise RuntimeError("the state directory must belong to your user")
    with (work / "lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"this lab is already running: {work}") from None
        manifest = work / "lab.json"
        fresh = not manifest.exists()
        if fresh:
            if set(work.iterdir()) != {work / "lock"}:
                raise RuntimeError("choose an empty state directory; existing files will not be replaced")
            work.chmod(0o700)
            (work / ".gitignore").write_text("*\n")
            save(manifest, {"version": 1, "phase": "preparing"})
            (work / "roots").mkdir()
            for name, variable in (("image", "NIX9_LAB_IMAGE"), ("bootstrap", "NIX9_LAB_BOOTSTRAP")):
                subprocess.run([os.environ["NIX9_LAB_NIX_STORE"], "--realise", os.environ[variable],
                                "--add-root", str(work / "roots" / name), "--indirect"], check=True)
        elif json.loads(manifest.read_text()) != {"version": 1, "phase": "ready"}:
            raise RuntimeError("initial setup did not finish; keep the logs and choose a new state directory")
        else:
            work.chmod(0o700)
        progress_output = sys.stdout

        def progress(message):
            print(message, file=progress_output, flush=True)

        with (work / "control.log").open("a") as log, redirect_stdout(log), redirect_stderr(log):
            lab = Lab(work, progress)
            save(work / "run.json", {"pid": os.getpid(), "phase": "starting"})
            try:
                if fresh:
                    provision(lab)
                    save(manifest, {"version": 1, "phase": "ready"})
                else:
                    for name in MACHINES:
                        lab.start(name)
                lab.consoles()
                save(work / "run.json", {"pid": os.getpid(), "phase": "ready", "consoles": {
                    name: str(lab.sockets / name) for name in MACHINES}})
                progress(f"Lab ready in {work}\nConnect: nix run .#lab -- console auth {shlex.quote(str(work))}\n"
                         "At auth: rcpu -u alice -h build\nCtrl-C here stops the lab and preserves its disks.")
                while True:
                    time.sleep(1)
                    for name, guest in lab.guests.items():
                        if not guest.child.isalive():
                            raise RuntimeError(f"{name} stopped unexpectedly; see {work / 'control.log'}")
                        try:
                            guest.child.read_nonblocking(size=65536, timeout=0)
                        except pexpect.TIMEOUT:
                            pass
            finally:
                previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
                termination = signal.signal(signal.SIGTERM, signal.SIG_IGN)
                try:
                    lab.close()
                finally:
                    (work / "run.json").unlink(missing_ok=True)
                    signal.signal(signal.SIGINT, previous)
                    signal.signal(signal.SIGTERM, termination)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Run a persistent four-machine nix9 development lab.")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("run", help="prepare or resume the lab; Ctrl-C shuts it down")
    start.add_argument("directory", nargs="?", default="nix9-lab")
    attach = commands.add_parser("console", help="attach a machine's serial console; Ctrl-] detaches")
    attach.add_argument("machine", choices=MACHINES)
    attach.add_argument("directory", nargs="?", default="nix9-lab")
    status = commands.add_parser("status", help="show whether the lab is running")
    status.add_argument("directory", nargs="?", default="nix9-lab")
    arguments = sys.argv[1:]
    if not arguments or arguments[0] not in ("run", "console", "status", "-h", "--help"):
        arguments.insert(0, "run")
    args = parser.parse_args(arguments)
    work = Path(args.directory).resolve()
    try:
        if args.command == "run":
            def terminate(signum, frame):
                raise KeyboardInterrupt
            signal.signal(signal.SIGTERM, terminate)
            run(work)
        elif args.command == "console":
            console(work, args.machine)
        else:
            if not (work / "lab.json").exists():
                raise RuntimeError(f"no lab in {work}")
            with (work / "lock").open("r") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    state = (json.loads((work / "run.json").read_text())["phase"]
                             if (work / "run.json").exists() else "starting")
                else:
                    state = "stopped"
            print(state)
            for name, address in ADDRESSES.items():
                print(f"{name:5} {address}")
    except KeyboardInterrupt:
        if args.command != "run":
            return
        manifest = work / "lab.json"
        if manifest.exists() and json.loads(manifest.read_text()).get("phase") == "ready":
            print("Lab stopped. Run the same command to resume.")
        else:
            print(f"Initial setup stopped; state and logs remain in {work}. Use a new directory to start again.")
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError, pexpect.ExceptionPexpect) as error:
        parser.exit(1, f"lab: {error}\nSee {work / 'control.log'} for guest output.\n")


if __name__ == "__main__":
    main()
