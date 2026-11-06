"""Ordinary users offload real builds through two authenticated shared stores."""

from pathlib import Path
import json
import os
import re
import secrets
import signal
import time

from lab_updates import detach, quote


def output_path(output):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", output)
    if len(paths) != 1:
        raise RuntimeError("expected one remote output: " + output)
    return paths[0]


def remote(auth, user, command, expected=None):
    return auth.command("rcpu -u " + user + " -h build -c " + quote(command), expected)


def build(auth, user, label, attribute="package"):
    return remote(auth, user, "nix-build /n/projects/builders.nix -A " + attribute
                  + " --argstr label " + label)


def check_builders(auth):
    fixture = Path(__file__).with_name("lab-builders.nix").read_bytes()
    # Transfer literal bytes across both rc parsers, including Nix interpolation.
    for offset in range(0, len(fixture), 64):
        chunk = fixture[offset:offset + 64]
        program = 'BEGIN { printf "' + '%c' * len(chunk) + '",' + ','.join(map(str, chunk)) + ' }'
        remote(auth, "alice", "awk " + quote(program) + (" > " if offset == 0 else " >> ")
               + "/n/projects/builders.nix")
    remote(auth, "alice", "chmod 660 /n/projects/builders.nix")
    records = {}
    run = secrets.token_hex(4)
    for user in ("alice", "bob"):
        label = user + "-" + run
        print("Building through the shared daemon as " + user + "...", flush=True)
        log = build(auth, user, label)
        package = output_path(log)
        if " on 'cpu://" not in log:
            raise RuntimeError("build was not dispatched to the CPU builder: " + log)
        remote(auth, user, "cat " + package + "/builder; echo", "batch")
        remote(auth, user, "cat " + package + "/identity; echo", "none")
        remote(auth, user, package + "/bin/hello", "hello from the shared workspace")
        environment = output_path(build(auth, user, label, "environment"))
        remote(auth, user, "roots=`{nix-store --roots-dir}; nix-profile $roots/distributed set "
               + environment + "; . " + environment + "/activate && hello", "hello from the shared workspace")
        records[user] = {"label": label, "package": package, "environment": environment}
    reused = build(auth, "bob", records["alice"]["label"])
    if output_path(reused) != records["alice"]["package"] or "building '" in reused or "copying path" in reused:
        raise RuntimeError("Bob did not reuse Alice's remote result: " + reused)
    for user in ("alice", "bob"):
        remote(auth, user, "test ! -r /adm/builder.keys && test ! -w /usr/local/nix/store")
        remote(auth, user, "nix-store --roots-dir", "/usr/local/nix/state/gcroots/per-user/" + user)
    print("PASS: Alice and Bob offload C builds, share results and retain separate profiles", flush=True)
    return records


def check_builder_restart(auth, records):
    for user, record in records.items():
        remote(auth, user, "roots=`{nix-store --roots-dir}; cat $roots/distributed", record["environment"])
        reused = build(auth, user, record["label"])
        if output_path(reused) != record["package"] or "building '" in reused or "copying path" in reused:
            raise RuntimeError("restart did not retain the remote result: " + reused)
    fresh = output_path(build(auth, "alice", records["alice"]["label"] + "-restart"))
    remote(auth, "alice", "cat " + fresh + "/builder; echo", "batch")
    print("PASS: restart retains remote outputs and profiles and restores builder credentials", flush=True)


def check_builder_unavailable(work, auth, attach, records):
    running = json.loads((work / "run.json").read_text())
    children = Path(f"/proc/{running['pid']}/task/{running['pid']}/children").read_text().split()
    machines = []
    for pid in children:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if args[0].endswith(b"qemu-system-x86_64") and any(
                arg.startswith(("file=" + str(work / "batch.qcow2") + ",").encode()) for arg in args):
            machines.append(int(pid))
    if len(machines) != 1:
        raise RuntimeError("cannot identify the lab's batch VM")
    batch = attach("batch")
    try:
        batch.child.sendline("fshalt")
        batch.child.expect("done halting", timeout=120)
        detach(batch)
        batch = None
        os.kill(machines[0], signal.SIGTERM)
        deadline = time.monotonic() + 30
        while json.loads((work / "run.json").read_text())["machines"]["batch"]["state"] != "stopped":
            if time.monotonic() > deadline:
                raise RuntimeError("the lab did not report the stopped CPU")
            time.sleep(.2)
        for user, record in records.items():
            reused = build(auth, user, record["label"])
            if output_path(reused) != record["package"] or "building '" in reused or "copying path" in reused:
                raise RuntimeError("cached result required the unavailable builder: " + reused)
        command = "nix-build /n/projects/builders.nix -A package --argstr label " + records["alice"]["label"] + "-unavailable"
        started = time.monotonic()
        output = remote(auth, "alice", "rc -c " + quote(command) + "; echo BUILDER-ERROR:$status")
        if (not re.search(r"(?m)^BUILDER-ERROR:.+", output)
                or "connection setup timed out after 30 seconds" not in output
                or time.monotonic() - started > 45):
            raise RuntimeError("unavailable builder did not fail clearly: " + output)
        print("PASS: cached results work without the builder and new remote-only builds fail clearly", flush=True)
    finally:
        if batch is not None:
            detach(batch)
