"""Exercise the public lab launcher and consoles across a complete shutdown."""

from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

import pexpect

from guest import Guest
from lab_updates import check_updates
from lab_builders import check_builders, check_builder_restart, check_builder_unavailable


launcher, output = sys.argv[1:]
Path(output).mkdir(parents=True, exist_ok=True)
prompt = r"(?m)^(?:[a-z0-9-]+[%#] |% )"


def output_path(result):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", result)
    if len(paths) != 1:
        raise RuntimeError("expected one environment: " + result)
    return paths[0]


state = os.environ.get("NIX9_LAB_TEST_STATE")
with (nullcontext(None) if state else tempfile.TemporaryDirectory()) as temporary:
    work = Path(state).resolve() if state else Path(temporary) / "lab"
    log_path = Path(output) / "launcher.log"
    environments = {}

    def start():
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
                time.sleep(0.5)
        except BaseException:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=600)
            log.close()
            raise

    def attach(machine="auth"):
        child = pexpect.spawn(launcher, ["console", machine, str(work)], encoding="utf-8", timeout=600)
        child.logfile_read = sys.stdout
        child.expect("Ctrl-] detaches.")
        child.sendline("")
        child.expect(prompt)
        return Guest(child, prompt)

    def stop(process, log):
        process.send_signal(signal.SIGINT)
        try:
            if process.wait(timeout=600) != 0:
                raise RuntimeError("lab shutdown failed; see " + str(log_path))
        finally:
            log.close()
        if (work / "run.json").exists():
            raise RuntimeError("lab retained a running marker after shutdown")

    process = None
    try:
        process, log = start()
        refused = subprocess.run([launcher, str(work)], capture_output=True, text=True)
        if refused.returncode == 0 or "already running" not in refused.stderr:
            raise RuntimeError("a second launcher did not refuse the active lab")
        auth = attach()
        auth.child.send("echo LINE-EDITX\x7f\r")
        auth.child.expect(r"(?m)^LINE-EDIT\r*$")
        auth.child.expect(prompt)
        auth.child.sendline("sleep 30")
        time.sleep(0.5)
        auth.child.sendcontrol("c")
        auth.child.expect(prompt, timeout=10)
        auth.command("rcpu -u alice -h build -c 'echo retained > /n/projects/retained; "
                     "chmod 660 /n/projects/retained'")
        for machine in ("build", "batch"):
            environment = output_path(auth.command("rcpu -u alice -h " + machine
                + " -c 'cd /n/projects/hello && nix-build environment.nix'"))
            environments[machine] = environment
            auth.command("rcpu -u alice -h " + machine + " -c 'roots=`{nix-store --roots-dir}; "
                         "nix-profile $roots/environment set " + environment + "; . " + environment
                         + "/activate && hello'", "hello from the shared workspace")
            auth.command("rcpu -u bob -h " + machine + " -c 'cat /n/projects/retained'", "retained")
        distributed = check_builders(auth)
        selected = check_updates(work, attach, auth)
        # Leave the public console in a CPU login. Shutdown uses a separate UART.
        auth.child.sendline("rcpu -u alice -h build -c 'echo LAB-LOGIN; exec /bin/rc -i'")
        auth.child.expect(r"(?m)^LAB-LOGIN\r*$")
        stop(process, log)
        process = None
        auth.child.expect(pexpect.EOF)
        auth.child.close()
        status = subprocess.check_output([launcher, "status", str(work)], text=True)
        if not status.startswith("stopped\n"):
            raise RuntimeError("stopped lab status was incorrect")
        process, log = start()
        auth = attach()
        auth.command("rcpu -u alice -h build -c 'cat /cfg/nix9/files/lab; echo'", "updated")
        auth.command("rcpu -u alice -h build -c 'cat /usr/local/nix/state/gcroots/machines/build/system'", selected)
        files = attach("files")
        files.command("cd /cfg/nix9-lab; nix9 status --health build batch")
        files.child.sendcontrol("]")
        files.child.expect(pexpect.EOF)
        files.child.close()
        for machine, environment in environments.items():
            auth.command("rcpu -u bob -h " + machine + " -c 'cat /n/projects/retained'", "retained")
            auth.command("rcpu -u alice -h " + machine + " -c 'roots=`{nix-store --roots-dir}; "
                         "cat $roots/environment'", environment)
            reused = auth.command("rcpu -u alice -h " + machine
                                  + " -c 'cd /n/projects/hello && nix-build environment.nix'")
            if output_path(reused) != environment or "building '" in reused or "copying path" in reused:
                raise RuntimeError(machine + ": restart did not reuse the original environment")
        check_builder_restart(auth, distributed)
        check_builder_unavailable(work, auth, attach, distributed)
        auth.child.sendcontrol("]")
        auth.child.expect(pexpect.EOF)
        auth.child.close()
        stop(process, log)
        process = None
        Path(output, "results.json").write_text(json.dumps({
            "status": "passed", "machines": 4,
            "checks": ["first-setup", "serial-console", "console-line-editing", "console-interrupt", "duplicate-launch-rejected", "two-cpu-builds",
                       "shared-project", "profiles", "shutdown-during-cpu-login", "restart",
                       "system-update", "retained-system-generation", "retained-files",
                       "retained-profiles", "cached-builds-after-restart", "deployment-via-files",
                       "selected-and-booted-status", "individual-cpu-reboot", "console-after-reboot",
                       "continuous-batch-session", "single-cpu-rollback", "deployment-status-after-restart",
                       "multiuser-remote-builds", "remote-result-reuse", "remote-user-profiles",
                       "remote-builds-after-restart", "cached-builds-without-builder", "unavailable-builder-failure"],
        }, indent=2) + "\n")
    finally:
        if process is not None and process.poll() is None:
            stop(process, log)
        if (work / "control.log").exists():
            # Keep native diagnostics after disposable disks and credentials disappear.
            import shutil
            shutil.copyfile(work / "control.log", Path(output) / "control.log")
