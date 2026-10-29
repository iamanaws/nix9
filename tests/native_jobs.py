"""Run native cron across selections and retain an in-flight job through GC."""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from guest import boot, files_guest

ROOT = "/usr/local/nix/state/gcroots/machines/test/system"
LOG = "/sys/log/nix9-jobs/glenda/local.log"


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def reject(guest, command, reason):
    output = guest.command("rc -c " + quote(command) + "; echo JOB-ERROR:$status")
    if not re.search(r"(?m)^JOB-ERROR:.+", output) or reason not in output:
        raise RuntimeError(f"did not reject {reason}: {output}")


def wait_for(guest, command, pattern, timeout=85):
    deadline = time.monotonic() + timeout
    while True:
        output = guest.command(command + "; status=''")
        if re.search(pattern, output, re.M):
            return output
        if time.monotonic() > deadline:
            guest.command("cat /sys/log/cron")
            guest.command("ps -a")
            raise RuntimeError(f"timed out waiting for {pattern}: {output}")
        time.sleep(2)


def cron_pid(guest):
    output = guest.command("ps | awk '$NF == \"cron\" {print $2}'")
    values = re.findall(r"(?m)^[0-9]+$", output)
    if len(values) != 1:
        raise RuntimeError(f"expected one cron: {output}")
    return values[0]


def selected(guest):
    output = guest.command("cat " + ROOT)
    return re.findall(r"(?m)^/usr/local/nix/store/\S+$", output)[0]


qemu, image, archive, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    disk = Path(directory) / "jobs.qcow2"
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2",
                    "-F", "qcow2", "-b", str(Path(image).resolve()), str(disk)], check=True)
    fixtures = {"bootstrap.tar": archive, "jobs.nix": Path(__file__).with_name("jobs.nix"),
                "job-checks.nix": Path(__file__).with_name("job-checks.nix")}
    with files_guest(qemu, disk, fixtures, snapshot=False) as guest:
        guest.child.timeout = 900
        guest.command("cd / && tar xf /tmp/bootstrap.tar")
        guest.command(". /usr/local/pkg/nix9/activate; nix9-rebuild init test")
        checks = guest.command("nix-instantiate --eval --strict --json /tmp/job-checks.nix")
        if '\"status\":\"passed\"' not in checks:
            raise RuntimeError(checks)
        guest.command("if(test -e /adm/keys) rm /adm/keys; echo -n > /adm/keys; chmod 600 /adm/keys")
        guest.command("ls -ld /adm/keys | awk '{print $1}'", "--rw-------")
        for name in ("one", "two", "failed", "removed", "disabled", "long"):
            guest.command(f"echo '(import ./jobs.nix {{}}).{name}' > /tmp/{name}.nix")
        guest.command("nix9-rebuild build /tmp/one.nix")
        one = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat " + ROOT + "-build"))[0]
        guest.command("nix9-rebuild check " + one)
        guest.command("test ! -e /sys/log/nix9-jobs/glenda && test ! -e " + ROOT)
        guest.command("nix9-rebuild select " + one)
        guest.command("ls -ld /sys/log/nix9-jobs/glenda | awk '{print $1}'", "d-rwx------")
        # The same boot entrypoint can be invoked here while caphash is available.
        # The distributed sharing test covers invocation by native CPU startup.
        guest.command(". /usr/local/pkg/nix9/system")
        cron = re.findall(r"(/usr/local/nix/store/[^ ]+-auth/bin/auth/cron)", guest.command("cat $nix9System/services/cron/start"))[0]
        guest.command(cron + " -d -s " + ROOT, "user glenda")
        guest.command("rc $nix9System/services/cron/start")
        pid = cron_pid(guest)
        reject(guest, "rc $nix9System/services/cron/start", "cron already running")
        wait_for(guest, "cat " + LOG + " >[2]/dev/null", "^local-one$")
        wait_for(guest, "cat " + LOG, r"^end .*status=$")
        guest.command("ls -ld " + LOG + " | awk '{print $1}'", "a-rw-------")
        wait_for(guest, "ls /usr/local/nix/state/gcroots/jobs/glenda | wc -l | awk '{print $1}'", "^0$", timeout=20)
        guest.command("nix9-rebuild switch /tmp/two.nix")
        two = selected(guest)
        wait_for(guest, "cat " + LOG, "^local-two$")
        if cron_pid(guest) != pid:
            raise RuntimeError("selection restarted cron")
        guest.command("nix9-rebuild switch /tmp/failed.nix")
        wait_for(guest, "cat " + LOG, r"^end .*status=.*deliberate$")
        guest.command("nix9-rebuild switch /tmp/removed.nix")
        time.sleep(2)
        wait_for(guest, "ls /usr/local/nix/state/gcroots/jobs/glenda | wc -l | awk '{print $1}'", "^0$", timeout=20)
        guest.command("cp " + LOG + " /tmp/jobs-before-removal")
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            guest.command("cmp " + LOG + " /tmp/jobs-before-removal")
            time.sleep(5)
        count = guest.command("awk '/^intentional-failure$/ {n++} END {print n+0}' " + LOG)
        previous = int(re.findall(r"(?m)^[0-9]+$", count)[0])
        guest.command("nix9-rebuild rollback")
        wait_for(guest, "awk '/^intentional-failure$/ {n++} END {if(n>" + str(previous) + ") print \"ROLLBACK-JOB-RAN\"}' " + LOG, "^ROLLBACK-JOB-RAN$")
        guest.command("nix9-rebuild switch /tmp/long.nix")
        long_system = selected(guest)
        wait_for(guest, "cat " + LOG, "^retained-start$")
        roots = guest.command("cat /usr/local/nix/state/gcroots/jobs/glenda/local-*")
        task = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command(
            "cat " + long_system + "/services/cron/commands/local"))[0]
        if task not in roots or long_system not in roots:
            raise RuntimeError("job did not retain both its command and system")
        guest.command("nix9-rebuild switch /tmp/disabled.nix")
        history = guest.command("nix9-rebuild list")
        generations = [line.split()[0] for line in history.splitlines()
                       if line.endswith(long_system) and re.match(r"^[0-9]+ ", line)]
        if len(generations) != 1:
            raise RuntimeError(f"missing long-job generation: {history}")
        guest.command("nix9-rebuild delete " + generations[0])
        guest.command("nix-store --gc")
        guest.command("nix-store --check-validity " + task + " " + long_system)
        guest.command("test -f " + task + "/command")
        guest.command("echo finish > /tmp/job-finish")
        wait_for(guest, "cat " + LOG, "^retained-end$", timeout=20)
        wait_for(guest, "ls /usr/local/nix/state/gcroots/jobs/glenda | wc -l | awk '{print $1}'", "^0$", timeout=20)
        guest.command("cp " + LOG + " /tmp/jobs-before-disable")
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            guest.command("cmp " + LOG + " /tmp/jobs-before-disable")
            time.sleep(5)
        if cron_pid(guest) != pid:
            raise RuntimeError("disabling jobs replaced the scheduler")
        print("PASS: native capabilities, live updates, failure status, removal, rollback, disabling and in-flight GC roots", flush=True)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps({
        "status": "passed", "firstSystem": one, "secondSystem": two,
        "retainedTask": task, "checks": ["typed-evaluation", "preflight-no-mutations",
        "native-user-capabilities", "single-scheduler", "private-logs", "live-update",
        "failure-status", "removed-jobs", "rollback", "disable", "in-flight-gc-root", "root-cleanup"]
    }, indent=2) + "\n")
