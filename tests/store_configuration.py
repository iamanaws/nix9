"""Selection changes new daemon connections while preserving existing workers."""

import re
import time


def check_configuration(guest, login, root):
    state = "/usr/local/nix/state/daemon/store"
    guest.command("mkdir /tmp/configuration-request; echo '~ 1 1' >/tmp/configuration-request/request.rc")
    guest.command("mkdir /usr/nix9-configuration-client; echo 'substitute = false' >/usr/nix9-configuration-client/nix.conf")
    client_defaults = ("NIX_CONF_DIR=/usr/nix9-configuration-client; NIX_USER_CONF_FILES=/dev/null; NIX_CONFIG=(); ")

    def target_status(expected):
        return guest.command("rc $nix9/packages/installation/target.rc status configuration-test "
                             "store store - /tmp/configuration-request", expected)

    def current():
        output = guest.command("$nix9/bin/nix-store-service -Q " + state)
        paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", output)
        if len(paths) != 1:
            raise RuntimeError("invalid active configuration: " + output)
        return paths[0]

    def until(command, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = guest.command("if(" + command + ") echo CONFIGURATION-READY; status=''")
            if re.search(r"(?m)^CONFIGURATION-READY$", result):
                return
            time.sleep(0.1)
        raise RuntimeError("configuration test timed out: " + command)

    before = current()
    target_status("store nix-config " + before)
    for name in ("live", "invalidLive"):
        guest.command(f"nix-build /tmp/{name}.nix --no-out-link > /tmp/{name}")
    guest.command("nix-build /usr/store-service.nix -A delay --no-out-link")
    for action in ("check", "select"):
        output = guest.command(f"nix9 {action} /tmp/invalidLive; echo CONFIGURATION-ERROR:$status")
        if "invalid Nix settings" not in output or not re.search(r"(?m)^CONFIGURATION-ERROR:.+", output):
            raise RuntimeError("invalid live configuration was accepted: " + output)
        guest.command("~ `{cat " + root + "} `{cat " + root + "-boot}")
        if current() != before:
            raise RuntimeError("invalid settings changed the active configuration")
    guest.command("nix9 check /tmp/live")
    if current() != before:
        raise RuntimeError("check changed the active configuration")
    login(guest, "alice", "test ! -w " + state + "; test ! -w " + state + "/1")
    output = login(guest, "alice", "$nix9/bin/nix-store-service -U " + state + " " + before
                   + " || echo CONFIGURATION-ERROR:$status")
    if "only the store owner" not in output:
        raise RuntimeError("ordinary user changed daemon configuration: " + output)
    # An interrupted writer never becomes a configuration, even with a higher sequence.
    guest.command("echo interrupted > " + state + "/99; chmod 600 " + state + "/99")
    if current() != before:
        raise RuntimeError("an unfinished record became active")
    guest.command("echo /tmp/configuration > " + state + "/100; chmod 444 " + state + "/100")
    output = guest.command("$nix9/bin/nix-store-service -Q " + state + "; echo CONFIGURATION-ERROR:$status")
    if "invalid daemon configuration path" not in output:
        raise RuntimeError("an unsafe committed path was accepted: " + output)
    guest.command("rm " + state + "/100")
    guest.command("fn configurationJob { /amd64/bin/auth/as alice /bin/rc -el -c "
                  "'nix-build /usr/store-service.nix -A held --no-out-link'; echo $status >/tmp/configuration-held.status }")
    guest.command("@{ configurationJob >/tmp/configuration-held.log >[2=1] } &")
    until("grep -s CONFIGURATION-BUILD-READY /tmp/configuration-held.log")
    output = guest.command("ps | awk '$NF == \"nix-daemon-worker\" {print $2}'")
    workers = re.findall(r"(?m)^\d+$", output)
    if not workers:
        raise RuntimeError("missing held worker: " + output)
    try:
        guest.command("nix9 select /tmp/live")
        after = current()
        if after == before:
            raise RuntimeError("selection did not apply eligible settings")
        guest.command("nix9 status", "nix-config-reboot no")
        target_status("store nix-config " + after)
        guest.command("~ `{cat " + root + "-boot} `{cat " + root + ".generations/1}")
        for worker in workers:
            namespace = guest.command("cat /proc/" + worker + "/ns")
            if before + "/files" not in namespace or after + "/files" in namespace:
                raise RuntimeError("existing worker lost its configuration snapshot: " + namespace)
    finally:
        guest.command("echo release > /usr/configuration-release; chmod 644 /usr/configuration-release")
    until("test -f /tmp/configuration-held.status")
    guest.command("grep -s '^$' /tmp/configuration-held.status")
    # Do not send selected client settings: exercise the daemon's own new defaults.
    login(guest, "bob", client_defaults + "nix-build /usr/store-service.nix -A feature --argstr featureName live --no-out-link")
    output = login(guest, "alice", client_defaults + "nix-build /usr/store-service.nix -A slow --no-out-link || echo CONFIGURATION-ERROR:$status")
    if "timed out" not in output or not re.search(r"(?m)^CONFIGURATION-ERROR:.+", output):
        raise RuntimeError("new worker did not use the selected timeout: " + output)
    guest.command("nix9-rebuild rollback")
    if current() != before:
        raise RuntimeError("rollback did not restore daemon settings")
    output = login(guest, "alice", client_defaults + "nix-build /usr/store-service.nix -A feature --argstr featureName rollback "
                   "--no-out-link || echo CONFIGURATION-ERROR:$status")
    if "live" not in output or not re.search(r"(?m)^CONFIGURATION-ERROR:.+", output):
        raise RuntimeError("new worker did not use rolled-back features: " + output)
    guest.command("test -r /usr/local/nix/state/gcroots/machines/store/daemon-configs/`{basename " + after + "}")
    guest.command("nix9-rebuild delete 2; rm /tmp/live")
    until("test `{ls /usr/local/nix/state/db/clients | wc -l} -eq 0")
    guest.command("nix-store --gc")
    guest.command("nix-store --check-validity " + after)
    guest.command("nix9 status", "nix-config-reboot no")
    print("PASS: invalid settings, worker snapshots, live defaults, owner-only publication, rollback and retained snapshots", flush=True)
