"""Shared disposable serial-console guest for package builds and smoke tests."""

import contextlib
import re
import sys

import pexpect


class Guest:
    def __init__(self, child):
        self.child = child

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


class SerialLog:
    def write(self, data):
        # Nix's log renderer treats CR as erase-line; the guest emits CR/CR/LF.
        sys.stdout.write(data.replace("\r", ""))
        sys.stdout.flush()

    def flush(self):
        sys.stdout.flush()


@contextlib.contextmanager
def boot(qemu, disk):
    child = pexpect.spawn(
        qemu,
        [
            "-enable-kvm", "-m", "2G", "-smp", "2",
            "-display", "none", "-monitor", "none", "-serial", "stdio",
            "-snapshot", "-drive", f"file={disk},format=qcow2,if=virtio",
            "-nic", "user",
        ],
        encoding="utf-8",
        codec_errors="replace",
        timeout=120,
    )
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
        child.sendline("fshalt")
        child.expect("done halting")
    finally:
        child.close(force=True)
