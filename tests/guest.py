"""Shared disposable serial-console guest for package builds and smoke tests."""

import contextlib
import functools
import http.server
from pathlib import Path
import shutil
import tempfile
import threading
import re
import signal
import sys

import pexpect


class Guest:
    def __init__(self, child):
        self.child = child
        self.crashed = False

    def crash(self):
        """Cut VM power without giving the guest a chance to close files."""
        self.child.kill(signal.SIGKILL)
        self.child.expect(pexpect.EOF)
        self.crashed = True

    def command(self, command, expected=None):
        self.child.sendline(command + "; echo NIX9-STATUS:$status")
        self.child.expect(r"(?m)^NIX9-STATUS:([^\n]*)\n")
        output = self.child.before
        status = self.child.match.group(1).rstrip("\r")
        self.child.expect(r"(?m)^term% ")
        if status:
            raise RuntimeError(f"guest command failed ({status}): {command}")
        if expected is not None and not re.search(
            r"(?m)^" + re.escape(expected) + r"\r*$", output
        ):
            raise RuntimeError(f"missing guest output {expected!r}: {command}")
        return output.replace("\r", "")


class SerialLog:
    def write(self, data):
        # Nix's log renderer treats CR as erase-line; the guest emits CR/CR/LF.
        sys.stdout.write(data.replace("\r", ""))
        sys.stdout.flush()

    def flush(self):
        sys.stdout.flush()


@contextlib.contextmanager
def boot(qemu, disk, *, snapshot=True, forward_port=None):
    network = "user"
    if forward_port is not None:
        network += f",hostfwd=tcp:127.0.0.1:{forward_port}-:17010"
    child = pexpect.spawn(
        qemu,
        [
            "-enable-kvm", "-m", "2G", "-smp", "2",
            "-display", "none", "-monitor", "none", "-serial", "stdio",
            "-drive", f"file={disk},format=qcow2,if=virtio",
            "-nic", network,
        ] + (["-snapshot"] if snapshot else []),
        encoding="utf-8",
        codec_errors="replace",
        timeout=120,
    )
    # QEMU can take longer than ptyprocess's 0.1s default to release a VM.
    child.ptyproc.delayafterterminate = 1
    child.logfile_read = SerialLog()
    try:
        child.expect("bootargs is")
        child.sendline("")
        child.expect(r"user\[[^\]]*\]:")
        child.sendline("")
        child.expect(r"(?m)^term% ")
        guest = Guest(child)
        guest.command("ip/ipconfig ether /net/ether0")
        yield guest
        if not guest.crashed:
            child.sendline("fshalt")
            child.expect("done halting")
    finally:
        child.close(force=True)


@contextlib.contextmanager
def files_guest(qemu, disk, files):
    """Boot a guest and copy host fixtures into /tmp."""
    with tempfile.TemporaryDirectory() as directory:
        for name, source in files.items():
            shutil.copyfile(source, Path(directory) / name)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with boot(qemu, disk) as guest:
                    guest.child.timeout = 300
                    for name in files:
                        guest.command(f"hget -o /tmp/{name} http://10.0.2.2:{server.server_port}/{name}")
                    yield guest
            finally:
                server.shutdown()
                thread.join()
