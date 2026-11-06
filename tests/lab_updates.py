"""Deploy, reboot and roll back one CPU while a second CPU stays in use."""

import json
from pathlib import Path
import re
import time

import pexpect


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def field(status, machine, name):
    matches = re.findall(r"(?m)^" + machine + " " + name + r" (\S+)$", status)
    if len(matches) != 1:
        raise RuntimeError(f"missing {machine} {name}: {status}")
    return matches[0]


def detach(guest):
    guest.child.sendcontrol("]")
    guest.child.expect(pexpect.EOF)
    guest.child.close()


def check_updates(work, attach, auth):
    files = attach("files")
    files.command(". /usr/local/pkg/nix9/system; cd /cfg/nix9-lab")
    cpu = attach("build")
    original = cpu.command("cat /usr/local/nix/state/gcroots/machines/build/system")
    original = re.findall(r"(?m)^/usr/local/nix/store/\S+$", original)
    if len(original) != 1:
        raise RuntimeError("missing original CPU system")
    original = original[0]
    states = json.loads((work / "run.json").read_text())["machines"]
    batch_boots = states["batch"]["boots"]

    worker = '''flag e +
echo $pid > $home/lab-worker.pid
6c -o $home/lab-worker.6 $src
6l -o $home/lab-worker $home/lab-worker.6
while(! test -e /n/projects/lab-stop) {
  $home/lab-worker >> $home/lab-heartbeat
  sleep 1
}
exit ''
'''
    # Keep the interactive console input on one line; rc indents quoted newlines.
    command = "; ".join("echo " + quote(line) + (" > " if index == 0 else " >> ")
                        + "/n/projects/lab-worker.rc" for index, line in enumerate(worker.splitlines()))
    command += "; chmod 660 /n/projects/lab-worker.rc"
    auth.command("rcpu -u alice -h build -c " + quote(command))
    auth.command("rcpu -u bob -h batch -c 'rm -f /usr/bob/lab-heartbeat /n/projects/lab-stop'")
    auth.command("rm -f /tmp/lab-batch.status")
    run = "cd /n/projects/hello && nix-shell --run 'rc /n/projects/lab-worker.rc'"
    auth.command("@{ rcpu -u bob -h batch -c " + quote(run)
                 + " </dev/null >/tmp/lab-batch.log >[2=1]; echo $status >/tmp/lab-batch.status } &")

    def alive():
        output = auth.command("if(test -e /tmp/lab-batch.status) { echo LAB-WORKER-EXITED; "
                              "cat /tmp/lab-batch.log }; status=''")
        if re.search(r"(?m)^LAB-WORKER-EXITED$", output):
            raise RuntimeError("batch development shell exited early:\n" + output)

    def activity():
        alive()
        text = auth.command("rcpu -u bob -h batch -c '"
                            "test -e /proc/`{cat $home/lab-worker.pid} && wc -l < $home/lab-heartbeat'")
        counts = re.findall(r"(?m)^\s*(\d+)\s*$", text)
        return int(counts[-1]) if counts else 0

    def until(operation, description, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if operation():
                return
            time.sleep(.5)
        raise RuntimeError("timed out waiting for " + description)

    def reboot():
        before = json.loads((work / "run.json").read_text())["machines"]["build"]["boots"]
        cpu.child.sendline("fshalt -r")

        def ready():
            states = json.loads((work / "run.json").read_text())["machines"]
            if states["batch"]["boots"] != batch_boots:
                raise RuntimeError("the other CPU was rebooted")
            return states["build"]["boots"] > before and states["build"]["state"] == "ready"

        until(ready, "CPU reboot and console recovery", timeout=300)
        cpu.child.expect(r"(?m)^(?:[a-z0-9-]+[%#] |% )", timeout=30)
        cpu.command("echo `{cat /dev/sysname}", "build")

    try:
        # The worker starts asynchronously; wait for compilation and its first read/write.
        def started():
            alive()
            return re.search(r"(?m)^LAB-ACTIVE$", auth.command(
                "if(rcpu -u bob -h batch -c 'test -s $home/lab-heartbeat') echo LAB-ACTIVE; status=''")
            )
        print("Waiting for the batch development shell...", flush=True)
        until(started, "batch development shell", timeout=600)
        first = activity()
        files.command("cp default.nix default-original.nix")
        awk = ('{ print; if ($1 == "machines" && $2 == "=") '
               'print "      build.configuration.files.lab = \\"updated\\";"; }')
        files.command("awk " + quote(awk) + " default-original.nix > default.nix")
        print("Deploying the CPU update from files...", flush=True)
        files.command("nix9 deploy build")
        status = files.command("nix9 status --health build batch")
        updated = field(status, "build", "selected")
        if updated == original or field(status, "build", "booted") != original:
            raise RuntimeError("deployment did not preserve the running generation: " + status)
        if field(status, "build", "reboot") != "required":
            raise RuntimeError("deployment did not report the pending reboot: " + status)
        print("Rebooting build into the update...", flush=True)
        reboot()
        status = files.command("nix9 status --health build batch")
        if field(status, "build", "booted") != updated or field(status, "build", "reboot") != "no":
            raise RuntimeError("reboot did not apply the deployed system: " + status)
        cpu.command("cat /cfg/nix9/files/lab; echo", "updated")
        if activity() <= first:
            raise RuntimeError("the batch worker made no progress during deployment")
        second = activity()
        print("Rolling back build while batch stays active...", flush=True)
        cpu.command("nix9-rebuild rollback")
        status = files.command("nix9 status --health build")
        if field(status, "build", "selected") != original or field(status, "build", "booted") != updated:
            raise RuntimeError("rollback did not preserve the running generation: " + status)
        reboot()
        status = files.command("nix9 status --health build batch")
        if field(status, "build", "selected") != original or field(status, "build", "booted") != original:
            raise RuntimeError("rollback reboot did not restore the original generation: " + status)
        cpu.command("test ! -e /cfg/nix9/files/lab")
        if activity() <= second:
            raise RuntimeError("the batch worker made no progress during rollback")
        detach(cpu)
        cpu = attach("build")
        cpu.command("nix9 status --health")
        # Leave an update selected so the whole-lab restart must apply it too.
        print("Selecting the update for the whole-lab restart...", flush=True)
        files.command("nix9 deploy build")
        status = files.command("nix9 status --health build")
        if field(status, "build", "selected") != updated or field(status, "build", "booted") != original:
            raise RuntimeError("redeployment did not select the update for restart: " + status)
        print("PASS: deployment and rollback reboot one CPU while a batch development shell stays active", flush=True)
    finally:
        auth.command("rcpu -u bob -h batch -c 'echo stop > /n/projects/lab-stop'")
        until(lambda: re.search(r"(?m)^LAB-DONE$", auth.command(
            "if(test -e /tmp/lab-batch.status) echo LAB-DONE; status=''")), "batch worker exit")
        auth.command("cat /tmp/lab-batch.status; test `{wc -c </tmp/lab-batch.status} -eq 1")
        detach(cpu)
        detach(files)
    return updated
