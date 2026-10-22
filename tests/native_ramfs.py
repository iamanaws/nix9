"""Build ramfs and check that private mounts and server processes disappear."""

import json
from pathlib import Path
import re
import sys
import time

from guest import files_guest


def servers(result):
    return set(re.findall(r"(?m)^\S+\s+(\d+)\s+.*\sramfs\s*$", result))


def session_roots(guest):
    result = guest.command("for(root in /usr/local/nix/state/gcroots/nix-session-*) if(test -f $root) echo $root; status=''")
    return re.findall(r"(?m)^/usr/local/nix/state/gcroots/nix-session-[^\s]+$", result)


def wait_for_servers(guest, expected):
    for attempt in range(20):
        if servers(guest.command("ps")) == expected and not session_roots(guest):
            return
        time.sleep(0.05)
    raise RuntimeError("session retained a server or GC root after exit")


qemu, image, archive, output = sys.argv[1:]
fixtures = {"bootstrap.tar": archive, "sessions.nix": Path(__file__).with_name("sessions.nix")}
roots = "/usr/local/nix/state/gcroots"
with files_guest(qemu, image, fixtures) as guest:
    guest.child.timeout = 600
    guest.command("cd / && tar xf /tmp/bootstrap.tar")
    guest.command(". /usr/local/pkg/nix9/activate")
    guest.command(f"nix-build $nix9/shell.nix --out-link {roots}/toolchain")
    guest.command("NIX_CONFIG='substituters ='")
    guest.command(f"nix-build $nix9/ramfs --out-link {roots}/ramfs")
    guest.command(f"environment=`{{cat {roots}/ramfs}}")
    for name in ("libauth", "libthread", "lib9p", "ramfs"):
        guest.command(f"nix-build '<nix9>' -A {name} --check --no-out-link")
    before = servers(guest.command("ps"))
    namespace = guest.command("cat /proc/$pid/ns")
    guest.child.timeout = 30
    if servers(guest.command("@{ . $environment/activate; ps }")) != before:
        raise RuntimeError("activation started a session")
    result = guest.command("$environment/session rc -c ps")
    if len(servers(result) - before) != 1:
        raise RuntimeError(f"missing live ramfs server: {result}")
    wait_for_servers(guest, before)
    for _ in range(2):
        guest.command("$environment/session rc $nix9/ramfs/run.rc", "Hello from ramfs")
        guest.command("test ! -f /mnt/hello")
        if guest.command("cat /proc/$pid/ns") != namespace:
            raise RuntimeError("service changed the parent namespace")
        wait_for_servers(guest, before)
    result = guest.command("$environment/session rc -c 'ps; exit deliberate'; echo SERVICE-STATUS:$status")
    if not re.search(r"(?m)^SERVICE-STATUS:.*deliberate$", result):
        raise RuntimeError(f"missing service failure: {result}")
    if len(servers(result) - before) != 1:
        raise RuntimeError(f"missing live ramfs server before failure: {result}")
    wait_for_servers(guest, before)
    if guest.command("cat /proc/$pid/ns") != namespace:
        raise RuntimeError("failed service changed the parent namespace")
    guest.command("test ! -f /mnt/hello")

    guest.command("$environment/session rc -c 'echo $pid > /tmp/nix9-session.pid; exec sleep 600' > /tmp/nix9-session.log &")
    guest.command("job=$apid; for(i in 1 2 3 4 5) if(! test -f /tmp/nix9-session.pid) sleep 1; test -f /tmp/nix9-session.pid")
    if len(servers(guest.command("ps")) - before) != 1:
        raise RuntimeError("missing live ramfs server before interruption")
    guest.command("echo interrupt > /proc/^$job^/note")
    guest.command("wait $job; test ! -e /proc/^$job")
    wait_for_servers(guest, before)
    if guest.command("cat /proc/$pid/ns") != namespace:
        raise RuntimeError("interrupted service changed the parent namespace")

    for name in ("configured", "failed"):
        guest.command(f"nix-build /tmp/sessions.nix --argstr packages $nix9/packages -A {name} --out-link {roots}/{name}")
        guest.command(f"{name}=`{{cat {roots}/{name}}}")
    guest.command("echo original > /tmp/nix9-session.conf")
    guest.command("$configured/session rc -c 'cat /tmp/nix9-session.conf; echo private > /mnt/hello'", "session configuration")
    guest.command("cat /tmp/nix9-session.conf", "original")
    guest.command("test ! -f /mnt/hello")
    result = guest.command("$failed/session rc -c 'echo unexpected > /tmp/nix9-started'; echo SERVICE-STATUS:$status")
    if not re.search(r"(?m)^SERVICE-STATUS:.*setup-failed$", result):
        raise RuntimeError(f"session setup failure was not propagated: {result}")
    guest.command("test ! -e /tmp/nix9-started")
    wait_for_servers(guest, before)
    if guest.command("cat /proc/$pid/ns") != namespace:
        raise RuntimeError("session setup changed the parent namespace")

    guest.child.sendline("$environment/session")
    guest.child.expect(r"(?m)^term% ")
    guest.child.sendline("echo interactive > /mnt/hello; cat /mnt/hello")
    guest.child.expect(r"(?m)^interactive\r*$")
    guest.child.expect(r"(?m)^term% ")
    guest.child.sendline("exit")
    guest.child.expect(r"(?m)^term% ")
    wait_for_servers(guest, before)
    guest.command("test ! -f /mnt/hello")
    if guest.command("cat /proc/$pid/ns") != namespace:
        raise RuntimeError("interactive session changed the parent namespace")

    guest.child.timeout = 300
    guest.command("touch /tmp/nix9-gc.conf")
    for ending in ("exit", "kill"):
        guest.command(f"nix-build /tmp/sessions.nix --argstr packages $nix9/packages -A gc --out-link {roots}/gc")
        guest.command(f"gc=`{{cat {roots}/gc}}")
        guest.child.sendline("$gc/session")
        guest.child.expect(r"(?m)^term% ")
        roots_in_use = session_roots(guest)
        if len(roots_in_use) != 1:
            raise RuntimeError(f"missing live session root: {roots_in_use}")
        guest.command(f"test `{{cat {roots_in_use[0]}}} '=' $gc")
        guest.command("data=`{cat /tmp/nix9-gc.conf}; cat $data", "retained")
        result = guest.command("echo $data")
        paths = re.findall(r"(?m)^(/usr/local/nix/store/[^/\s]+)/share/message$", result)
        if len(paths) != 1:
            raise RuntimeError(f"missing data dependency: {result}")
        data = paths[0]
        guest.command(f"rm {roots}/gc; nix-store --gc")
        guest.command("nix-store --verify-path $gc")
        guest.command("cat $data", "retained")
        guest.command("echo live > /mnt/hello; cat /mnt/hello", "live")
        if ending == "exit":
            guest.child.sendline("exit")
        else:
            guest.child.sendline("echo kill > /proc/$pid/note")
        guest.child.expect(r"(?m)^term% ")
        wait_for_servers(guest, before)
        guest.command("nix-store --gc; test ! -e $gc")
        guest.command(f"test ! -e {data}")
        if guest.command("cat /proc/$pid/ns") != namespace:
            raise RuntimeError("GC session changed the parent namespace")

    guest.command(f"nix-build /tmp/sessions.nix --argstr packages $nix9/packages -A gc --out-link {roots}/gc")
    guest.command(f"gc=`{{cat {roots}/gc}}")
    guest.command("$gc/session rc -c 'sleep 600 & echo $apid > /tmp/nix9-child.pid' > /tmp/nix9-child.log")
    guest.command("child=`{cat /tmp/nix9-child.pid}; test -e /proc/^$child")
    if len(session_roots(guest)) != 1:
        raise RuntimeError("session root did not survive in its child")
    guest.command(f"rm {roots}/gc; nix-store --gc; nix-store --verify-path $gc")
    guest.command(f"cat {data}/share/message", "retained")
    guest.command("echo kill > /proc/^$child^/note")
    guest.command("for(i in 1 2 3 4 5) if(test -e /proc/^$child) sleep 1; test ! -e /proc/^$child")
    wait_for_servers(guest, before)
    guest.command("nix-store --gc; test ! -e $gc")
    guest.command(f"test ! -e {data}")

    for arguments, reason in (("", "expected a store path"),
                              ("$configured/bin", "not in the Nix store")):
        result = guest.command(f"nix-build --run-session {arguments}; echo SERVICE-STATUS:$status")
        if reason not in result or not re.search(r"(?m)^SERVICE-STATUS:.+", result):
            raise RuntimeError(f"invalid session invocation was accepted: {result}")
    if session_roots(guest):
        raise RuntimeError("invalid session invocation left a GC root")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "ramfs": "native build, commands, interactive shell, configuration, GC retention, failure and interruption cleanup passed",
}, indent=2) + "\n")
