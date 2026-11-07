"""Wall-clock timing and ordinary interactive CPU/development sessions."""

from contextlib import contextmanager
import json
import re
import time

from guest import Guest


def quote(value):
    return "'" + value.replace("'", "''") + "'"


class Timings:
    def __init__(self, output):
        self.output = output
        self.samples = {}

    def record(self, name, seconds):
        seconds = round(seconds, 3)
        self.samples.setdefault(name, []).append(seconds)
        temporary = self.output / "timings.tmp"
        temporary.write_text(json.dumps(self.samples, indent=2) + "\n")
        temporary.replace(self.output / "timings.json")
        print(f"TIMING {name}: {seconds}s", flush=True)

    def measure(self, name, operation):
        started = time.monotonic()
        result = operation()
        self.record(name, time.monotonic() - started)
        return result


@contextmanager
def cpu_session(auth, machine):
    prompt = r"(?m)^nix9-cpu% "
    shell = "prompt=('nix9-cpu% ' ' '); exec /bin/rc -i"
    auth.child.sendline("rcpu -u alice -h " + machine + " -c " + quote(shell)
                        + "; echo NIX9-SESSION-EXIT:$status")
    auth.child.expect(prompt)
    session = Guest(auth.child, prompt)
    try:
        session.command("echo `{cat /dev/user}", "alice")
        yield session
    finally:
        auth.child.sendline("exit")
        auth.child.expect(r"(?m)^NIX9-SESSION-EXIT:([^\n]*)\n")
        status = auth.child.match.group(1).strip()
        auth.child.expect(auth.prompt)
        if status:
            raise RuntimeError("CPU session failed: " + status)


@contextmanager
def development_session(cpu, project, directory):
    shell = "cd " + directory + "; prompt=('nix9-development% ' ' '); exec /bin/rc -i"
    cpu.child.sendline("cd " + project + " && nix-shell default.nix --run " + quote(shell)
                       + "; echo NIX9-SHELL-EXIT:$status")
    prompt = r"(?m)^nix9-development% "
    cpu.child.expect(prompt)
    try:
        yield Guest(cpu.child, prompt)
    finally:
        cpu.child.sendline("exit")
        cpu.child.expect(r"(?m)^NIX9-SHELL-EXIT:([^\n]*)\n")
        status = cpu.child.match.group(1).strip()
        cpu.child.expect(cpu.prompt)
        if status:
            raise RuntimeError("development shell failed: " + status)
