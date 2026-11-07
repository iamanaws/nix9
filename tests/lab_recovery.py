"""Recover from an unreachable builder while a development shell stays open."""

from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import signal
import time

from lab_builders import build, output_path, remote
from lab_support import machine_pid
from lab_updates import detach, field, quote


def check_builder_recovery(work, auth, attach, records):
    running = json.loads((work / "run.json").read_text())
    batch = machine_pid(work, "batch")
    boots = {name: machine["boots"] for name, machine in running["machines"].items()}
    label = records["alice"]["label"] + "-recovery"
    directory = "/usr/alice/" + label
    script = "/n/projects/" + label + ".rc"
    job = "/tmp/" + label
    paused, started, saved = False, False, False

    def until(operation, description, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = operation()
            if result:
                return result
            time.sleep(.2)
        raise RuntimeError("timed out waiting for " + description)

    def alive():
        output = auth.command("if(test -f " + job + ".status) { echo RECOVERY-EXITED; cat "
                              + job + ".log }; status=''")
        if re.search(r"(?m)^RECOVERY-EXITED$", output):
            raise RuntimeError("development shell exited early: " + output)

    def shell(command):
        alive()
        remote(auth, "alice", "rm -f " + directory + "/status; echo " + quote(command)
               + " > " + directory + "/command")
        until(lambda: re.search(r"(?m)^RECOVERY-DONE$", remote(auth, "alice",
              "if(test -f " + directory + "/status) echo RECOVERY-DONE; status=''")), "shell command")
        result = remote(auth, "alice", "cat " + directory + "/output; echo -n RECOVERY-STATUS:; cat "
                        + directory + "/status")
        if not re.search(r"(?m)^RECOVERY-STATUS:$", result):
            raise RuntimeError("development command failed: " + result)
        alive()
        return result

    def compiled(output, machine):
        path = output_path(output)
        remote(auth, "alice", "cat " + path + "/builder; echo", machine)
        remote(auth, "alice", "cat " + path + "/identity; echo", "none")
        return path

    with ExitStack() as cleanup:
        files = attach("files")
        cleanup.callback(detach, files)
        owner = attach("build")
        cleanup.callback(detach, owner)
        files.command(". /usr/local/pkg/nix9/system; cd /cfg/nix9-lab")
        owner.command(". /usr/local/pkg/nix9/system")
        original = files.command("nix9 status build")
        system = field(original, "build", "selected")
        configuration = field(original, "build", "nix-config")
        if field(original, "build", "booted") != system:
            raise RuntimeError("builder recovery needs the selected system booted")
        remote(auth, "alice", "mkdir " + directory)
        fixture = Path(__file__).with_name("builder-recovery.rc").read_bytes()
        for offset in range(0, len(fixture), 64):
            chunk = fixture[offset:offset + 64]
            program = 'BEGIN { printf "' + '%c' * len(chunk) + '",' + ','.join(map(str, chunk)) + ' }'
            remote(auth, "alice", "awk " + quote(program) + (" > " if offset == 0 else " >> ") + script)
        run = "cd /n/projects/hello && nix-shell --run " + quote("rc " + script + " " + directory)
        try:
            auth.command("@{ rcpu -u alice -h build -c " + quote(run) + " </dev/null >" + job
                         + ".log >[2=1]; echo $status >" + job + ".status } &")
            started = True
            until(lambda: re.search(r"(?m)^RECOVERY-READY$", remote(auth, "alice",
                  "if(test -s " + directory + "/heartbeat) echo RECOVERY-READY; status=''")), "development shell", timeout=180)
            shell("~ $IN_NIX_SHELL impure && grep -s '^max-jobs = 0$' /cfg/nix9/files/nix.conf")
            pid = re.findall(r"(?m)^\d+$", remote(auth, "alice", "cat " + directory + "/pid"))
            if len(pid) != 1:
                raise RuntimeError("missing development shell identity")
            shell("6c -o hello.6 hello.c && 6l -o hello hello.6 && ./hello")
            # Pause only this VM: authentication, storage and build remain available.
            os.kill(batch, signal.SIGSTOP)
            paused = True
            for user, record in records.items():
                output = build(auth, user, record["label"])
                if output_path(output) != record["package"] or "building '" in output or "copying path" in output:
                    raise RuntimeError("cached result required the unreachable builder: " + output)
            command = "nix-build /n/projects/builders.nix -A package --argstr label " + label + "-unavailable"
            before = time.monotonic()
            output = remote(auth, "alice", "rc -c " + quote(command) + "; echo BUILDER-ERROR:$status")
            if (not re.search(r"(?m)^BUILDER-ERROR:.+", output)
                    or "connection setup timed out after 30 seconds" not in output
                    or time.monotonic() - before > 45):
                raise RuntimeError("unreachable builder did not fail clearly: " + output)
            files.command("cp default.nix default-before-recovery.nix")
            saved = True
            awk = ('{print; if ($1 == "machines" && $2 == "=") { '
                   'print "      build.configuration.nix.distributedBuilds = false;"; '
                   'print "      build.configuration.nix.settings.max-jobs = lib.mkForce 1;"; }}')
            files.command("awk " + quote(awk) + " default-before-recovery.nix > default.nix")
            print("Deploying local compilation while batch is unreachable...", flush=True)
            files.command("nix9 deploy build")
            status = files.command("nix9 status build")
            active = field(status, "build", "nix-config")
            if (field(status, "build", "selected") == system or field(status, "build", "booted") != system
                    or active == configuration or field(status, "build", "nix-config-selected") != active
                    or field(status, "build", "nix-config-reboot") != "no"):
                raise RuntimeError("deployment did not apply builder settings live: " + status)
            compiled(build(auth, "alice", label + "-fresh-local"), "build")
            stale = shell("package " + label + "-old-client || echo BUILDER-ERROR:$status")
            if not re.search(r"(?m)^BUILDER-ERROR:.+", stale):
                raise RuntimeError("old development shell unexpectedly discarded its client settings: " + stale)
            compiled(shell("package " + label + "-explicit-local --builders '' --max-jobs 1"), "build")
            shell(". /usr/local/pkg/nix9/system && grep -s '^max-jobs = 1$' /cfg/nix9/files/nix.conf")
            compiled(shell("package " + label + "-refreshed-local"), "build")
            shell("6c -o hello.6 hello.c && 6l -o hello hello.6 && ./hello")
            os.kill(batch, signal.SIGCONT)
            paused = False
            auth.command("rcpu -u bob -h batch -c 'echo RECOVERY-BATCH-READY'", "RECOVERY-BATCH-READY")
            print("Rolling back to remote compilation without reboot...", flush=True)
            owner.command("nix9-rebuild rollback")
            status = files.command("nix9 status build")
            if (field(status, "build", "selected") != system or field(status, "build", "booted") != system
                    or field(status, "build", "nix-config") != configuration
                    or field(status, "build", "nix-config-reboot") != "no"):
                raise RuntimeError("rollback did not restore remote builder defaults: " + status)
            compiled(build(auth, "bob", label + "-fresh-remote"), "batch")
            # Local capacity remains a client setting; an available remote
            # builder may still be preferred after the daemon rolls back.
            shell("grep -s '^max-jobs = 1$' /cfg/nix9/files/nix.conf")
            shell(". /usr/local/pkg/nix9/system && grep -s '^max-jobs = 0$' /cfg/nix9/files/nix.conf")
            compiled(shell("package " + label + "-refreshed-remote"), "batch")
            shell("~ $IN_NIX_SHELL impure && 6c -o hello.6 hello.c && 6l -o hello hello.6 && ./hello")
            if re.findall(r"(?m)^\d+$", remote(auth, "alice", "cat " + directory + "/pid")) != pid:
                raise RuntimeError("development shell was replaced during recovery")
            current = json.loads((work / "run.json").read_text())
            if {name: machine["boots"] for name, machine in current["machines"].items()} != boots:
                raise RuntimeError("builder recovery rebooted a machine")
            for user, record in records.items():
                remote(auth, user, "roots=`{nix-store --roots-dir}; cat $roots/distributed", record["environment"])
            print("PASS: live local recovery, client refresh and remote rollback preserve the development shell", flush=True)
        finally:
            if paused:
                os.kill(batch, signal.SIGCONT)
            if saved:
                files.command("cp default-before-recovery.nix default.nix")
            if started:
                remote(auth, "alice", "echo stop > " + directory + "/stop")
                until(lambda: re.search(r"(?m)^RECOVERY-DONE$", auth.command(
                      "if(test -f " + job + ".status) echo RECOVERY-DONE; status=''")), "development shell exit")
                auth.command("cat " + job + ".status; test `{wc -c <" + job + ".status} -eq 1")
