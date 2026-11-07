"""Public launcher and console operations shared by lab checks and benchmarks."""

import json
from pathlib import Path
import signal
import subprocess
import sys
import time

import pexpect

from guest import Guest


PROMPT = r"(?m)^(?:[a-z0-9-]+[%#] |% )"


def machine_pid(work, name):
    running = json.loads((work / "run.json").read_text())
    children = Path(f"/proc/{running['pid']}/task/{running['pid']}/children").read_text().split()
    machines = []
    for pid in children:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if args[0].endswith(b"qemu-system-x86_64") and any(
                arg.startswith(("file=" + str(work / (name + ".qcow2")) + ",").encode()) for arg in args):
            machines.append(int(pid))
    if len(machines) != 1:
        raise RuntimeError("cannot identify the lab's " + name + " VM")
    return machines[0]


def start_lab(launcher, work, log_path):
    log = log_path.open("a")
    process = subprocess.Popen([launcher, str(work)], stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 7200
    try:
        while True:
            if process.poll() is not None:
                raise RuntimeError("lab exited before readiness; see " + str(log_path))
            marker = work / "run.json"
            if marker.exists() and json.loads(marker.read_text())["phase"] == "ready":
                return process, log
            if time.monotonic() > deadline:
                raise RuntimeError("timed out preparing the lab")
            time.sleep(.5)
    except BaseException:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=600)
        log.close()
        raise


def attach_console(launcher, work, machine="auth"):
    child = pexpect.spawn(launcher, ["console", machine, str(work)], encoding="utf-8", timeout=600)
    child.logfile_read = sys.stdout
    child.expect("Ctrl-] detaches.")
    child.sendline("")
    child.expect(PROMPT)
    return Guest(child, PROMPT)


def detach_console(guest):
    guest.child.sendcontrol("]")
    guest.child.expect(pexpect.EOF)
    guest.child.close()


def stop_lab(process, log, work):
    process.send_signal(signal.SIGINT)
    try:
        if process.wait(timeout=600) != 0:
            raise RuntimeError("lab shutdown failed; see " + str(log.name))
    finally:
        log.close()
    if (work / "run.json").exists():
        raise RuntimeError("lab retained a running marker after shutdown")


def write_file(guest, path, data):
    # Literal bytes survive rc, including quotes and Nix interpolation.
    if not data:
        guest.command("echo -n > " + path)
    for offset in range(0, len(data), 64):
        chunk = data[offset:offset + 64]
        program = 'BEGIN { printf "' + '%c' * len(chunk) + '",' + ','.join(map(str, chunk)) + ' }'
        guest.command("awk '" + program + "' " + ("> " if offset == 0 else ">> ") + path)
