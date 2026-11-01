"""Exercise live checks on auth, CWFS, two CPUs and a terminal."""

import re
import signal
import time


def rejected(guest, command, expected):
    result = guest.command(command + "; echo HEALTH-ERROR:$status")
    if not re.search(r"(?m)^HEALTH-ERROR:.+", result) or expected not in result or "syntax error" in result:
        raise RuntimeError(f"health failure was not reported: {command}: {result}")
    if "!Adding key:" in result:
        raise RuntimeError("health checks prompted for credentials")
    return result


def history(guest):
    # Listener diagnostics can arrive on the console between foreground commands.
    result = re.findall(r"(?m)^[0-9]+ [* -] /usr/local/nix/store/\S+$",
                        guest.command("nix9-rebuild list"))
    if not result:
        raise RuntimeError("generation history is missing")
    return result


def check_health(*, stack, auth, files, builders, terminal, start, stop, listening):
    guests = {"auth": auth, "files": files, **builders, "terminal": terminal}
    histories = {name: history(guest) for name, guest in guests.items()}
    booted = {name: re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command(
        f"cat /usr/local/nix/state/gcroots/machines/{name}/system-boot"))[0]
        for name, guest in guests.items()}
    for name, guest in guests.items():
        result = guest.command("nix9 status --health", f"{name} health-result ok")
        if f"{name} health-system {booted[name]}\n" not in result:
            raise RuntimeError("health checks did not use the booted configuration")
    print("PASS: local checks for auth, CWFS, CPU, NDB and fresh TCP/TLS mounts", flush=True)

    root = "/usr/local/nix/state/gcroots/health-installation"
    terminal.command(f"nix-build /tmp/storage.nix -A initial.build --out-link {root}")
    terminal.command("mv /tmp/storage.nix /tmp/health-source.nix")
    command = f"nix9 status --health --from {root}"
    terminal.command("@{ status='' } > '#s/nix9-deploy-client-storage'")
    result = terminal.command(command + " build batch")
    for name in builders:
        if f"{name} health-result ok\n" not in result or f"{name} health cpu ok\n" not in result:
            raise RuntimeError(f"remote CPU health was not checked: {result}")
    terminal.command("test -e '#s/nix9-deploy-client-storage'; rm '#s/nix9-deploy-client-storage'")
    # Pending selections must not change what the running service check expects.
    files.command("nix9-rebuild switch /tmp/noDumps.nix")
    files.command("nix9 status --health", "files health-system " + booted["files"])
    files.command("nix9-rebuild rollback")
    histories["files"] = history(files)
    print("PASS: authenticated inventory checks, deployment lock independence and booted generation selection", flush=True)

    # A working 9P root must not hide a missing declared workspace directory.
    terminal.command("nix-build /tmp/health-path.nix --out-link /usr/local/nix/state/gcroots/health-path")
    terminal.command("pathCheck=`{cat /usr/local/nix/state/gcroots/health-path}")
    result = rejected(terminal, "rc -e $pathCheck/health terminal", "terminal health mount/work tcp!files!564 failed")
    if "missing-workspace" not in result:
        raise RuntimeError("the failing bound directory was absent from diagnostics")
    terminal.command("nix9 status --health", "terminal health-result ok")

    terminal.command("echo preserved > /usr/glenda/work/health-marker")
    terminal.command("echo 'delkey proto=dp9ik dom=nix9.storage role=client' > /mnt/factotum/ctl; cat /adm/health-bad.keys > /mnt/factotum/ctl")
    terminal.command("cat /usr/glenda/work/health-marker", "preserved")
    rejected(terminal, "nix9 status --health", "terminal health mount/work tcp!files!564 failed")
    terminal.command("echo 'delkey proto=dp9ik dom=nix9.storage role=client' > /mnt/factotum/ctl")
    rejected(terminal, "nix9 status --health", "terminal health mount/work tcp!files!564 failed")
    rejected(terminal, command + " build", "build health cpu failed")
    terminal.command("echo 'delkey proto=dp9ik dom=nix9.storage role=client' > /mnt/factotum/ctl; cat /adm/terminal.keys > /mnt/factotum/ctl")
    terminal.command("nix9 status --health", "terminal health-result ok")
    rejected(terminal, "@{ rfork n; bind /dev/null /net/cs; nix9 status --health }", "terminal health ndb/files failed")
    terminal.command("nix9 status --health", "terminal health-result ok")
    print("PASS: wrong credentials fail fresh authentication despite an existing mount; NDB errors remain local", flush=True)

    # A live but unresponsive provider must not hang the health command.
    files.child.kill(signal.SIGSTOP)
    began = time.monotonic()
    try:
        result = rejected(terminal, "nix9 status --health", "terminal health mount/work tcp!files!564 failed")
        if "terminal health mount/tools tcp!build!17020 ok" not in result:
            raise RuntimeError("a failed provider prevented checking another export")
    finally:
        files.child.kill(signal.SIGCONT)
    if time.monotonic() - began > 45:
        raise RuntimeError("health probes exceeded their time limits")
    terminal.command("nix9 status --health", "terminal health-result ok")
    stop(files)
    files = stack.enter_context(start("files"))
    guests["files"] = files
    listening(files, 564)
    terminal.command("nix9 status --health", "terminal health-result ok")
    print("PASS: bounded unresponsive-CWFS checks and fresh mounts after provider reboot", flush=True)

    stop(builders["batch"])
    result = rejected(terminal, command + " batch build", "batch health cpu failed")
    if "build health-result ok\n" not in result:
        raise RuntimeError("an unavailable CPU prevented checking another machine")
    builders["batch"] = stack.enter_context(start("batch"))
    guests["batch"] = builders["batch"]
    listening(builders["batch"], 17019)
    terminal.command(command + " batch build", "batch health-result ok")
    for name, guest in guests.items():
        if history(guest) != histories[name]:
            raise RuntimeError("health checks changed generation history")
        guest.command(f"cat /usr/local/nix/state/gcroots/machines/{name}/system", booted[name])
        namespace = guest.command("ns -r")
        if "/tmp/nix9-health-" in namespace or "/dev/null /dev/cons" in namespace:
            raise RuntimeError("a probe mount leaked into the caller's namespace")
        if "health-probe" in guest.command("ps -a"):
            raise RuntimeError("a health probe survived completion")
        guest.command("for(file in /tmp/nix9-health-*) test ! -e $file")
    print("PASS: unavailable CPU diagnostics, continued inspection, recovery and namespace/temp cleanup", flush=True)
    for guest in guests.values():
        stop(guest)
    return {
        "status": "passed", "machines": 5,
        "checks": ["booted-generation", "auth-listener", "cpu-listener", "cwfs-listener", "ndb-discovery",
                   "fresh-tcp-and-tls-mounts", "authenticated-remote-cpu", "deployment-lock-independence",
                   "missing-bound-directory", "wrong-credentials", "noninteractive-mount-and-cpu-auth",
                   "existing-mount-does-not-mask-failure", "ndb-failure",
                   "probe-timeouts", "provider-reboot", "unavailable-cpu", "continue-after-failure",
                   "recovery", "namespace-isolation", "temporary-cleanup"],
    }
