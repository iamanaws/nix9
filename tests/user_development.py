"""Shared-store development through authenticated logins on network-root CPUs."""

import re
import time


ROOTS = "/usr/local/nix/state/gcroots/per-user"
SCRIPT = "rc /usr/user-development.rc "
HELLO = "hello from the shared workspace"
USERS = ("alice", "bob")


def output_path(result):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", result)
    if len(paths) != 1:
        raise RuntimeError("expected one development output: " + result)
    return paths[0]


def until(guest, command, description, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = guest.command("if(" + command + ") echo DEVELOPMENT-READY; status=''")
        if re.search(r"(?m)^DEVELOPMENT-READY$", result):
            return
        time.sleep(0.2)
    raise RuntimeError("timed out waiting for " + description)


def idle(cpu):
    until(cpu, "test `{ls /usr/local/nix/state/db/clients | wc -l} -eq 0", "store clients to exit")
    until(cpu, "test `{ps | grep ' nix-store-service$' | wc -l} -eq 1", "store helpers to exit")


def check_profiles(remote, environments):
    for machine, environment in environments.items():
        for user in USERS:
            result = remote(user, SCRIPT + "profile", HELLO, machine=machine)
            if output_path(result) != environment:
                raise RuntimeError(f"{machine}: {user}'s profile changed")


def check_development(auth, cpus, remote, measure):
    environments = {}
    for machine, cpu in cpus.items():
        cpu.command("nix9 status --health", machine + " health nix/daemon ok")
        for user in USERS:
            remote(user, "echo `{cat /dev/user}", user, machine=machine)
            remote(user, "echo $NIX_REMOTE",
                   "daemon?address=tcp!127.0.0.1!17051&key-pattern=user=" + user, machine=machine)
            result = measure(machine + "/environment-" + user, lambda: remote(
                user, "nix-build /n/projects/hello/environment.nix", machine=machine))
            environment = output_path(result)
            if user == "alice":
                environments[machine] = environment
            elif environment != environments[machine] or "building '" in result:
                raise RuntimeError(machine + ": Bob did not reuse Alice's environment: " + result)
            remote(user, SCRIPT + "install", machine=machine)
        # User variables cannot change the identity used by daemon authentication.
        remote("alice", "user=bob; nix-store --roots-dir", ROOTS + "/alice", machine=machine)
        tools = output_path(remote("alice", SCRIPT + "tools", machine=machine))
        if tools == environment:
            raise RuntimeError("the alternative environment did not change")
        remote("bob", SCRIPT + "profile", HELLO, machine=machine)
        if output_path(remote("alice", SCRIPT + "rollback", HELLO, machine=machine)) != environment:
            raise RuntimeError(machine + ": user profile rollback failed")
    check_profiles(remote, environments)

    # A user's roots belong to this CPU's store, even though their home is shared.
    remote("alice", "nix-build /n/projects/hello/environment.nix --out-link " + ROOTS + "/alice/this-cpu")
    cpus["batch"].command("test ! -e " + ROOTS + "/alice/this-cpu")
    remote("alice", "nix-store --delete-root " + ROOTS + "/alice/this-cpu")
    print("PASS: CPU logins select shared stores, reuse builds and keep independent user profiles and machine roots", flush=True)

    # Keep both users' shells open on both CPUs while their owners collect garbage.
    for machine in cpus:
        for user in USERS:
            name = user + "-" + machine
            auth.command("@{ rcpu -u " + user + " -h " + machine + " -c '" + SCRIPT + "hold " + machine
                         + "' </dev/null >/tmp/" + name + ".log >[2=1]; echo $status >/tmp/" + name + ".status } &")
    try:
        for machine, cpu in cpus.items():
            for user in USERS:
                until(auth, "rcpu -u " + user + " -h " + machine
                      + " -c 'test -f $home/development-" + machine + "/ready'", user + " shell on " + machine,
                      timeout=600)
                remote(user, "cat $home/development-" + machine + "/identity", user, machine=machine)
                cpu.command("test `{ls " + ROOTS + "/" + user + "/nix-shell-* | wc -l} -eq 1")
            idle(cpu)
            cpu.command("nix-store --gc")
            for user in USERS:
                cpu.command("nix-store --verify-path `{cat " + ROOTS + "/" + user + "/nix-shell-*}")
        for machine, cpu in cpus.items():
            for user in USERS:
                name = user + "-" + machine
                remote(user, "echo stop > $home/development-" + machine + "/stop", machine=machine)
                until(auth, "test -f /tmp/" + name + ".status", name + " logout")
                auth.command("test `{wc -c </tmp/" + name + ".status} -eq 1")
                auth.command("cat /tmp/" + name + ".log", HELLO)
                until(cpu, "test ! -e " + ROOTS + "/" + user + "/nix-shell-*", name + " shell roots to close")
            idle(cpu)
            cpu.command("nix-store --gc")
    except Exception:
        for machine, cpu in cpus.items():
            cpu.command("ps; cat /sys/log/nix9-store; echo")
            for user in USERS:
                name = "/tmp/" + user + "-" + machine
                auth.command("if(test -f " + name + ".status) cat " + name + ".status; cat " + name + ".log; echo")
        raise
    check_profiles(remote, environments)
    print("PASS: four simultaneous user shells compile C, retain dependencies through GC and release roots on logout", flush=True)
    return environments


def benchmark_development(remote, measure):
    # Every sample includes a fresh authenticated CPU login, as a terminal user
    # would invoke it. Measure that baseline separately; do not subtract it.
    # The preceding GC can collect build inputs. The first shell restores them;
    # subsequent samples measure reuse, with no further GC during measurement.
    for machine in ("build", "batch"):
        def sample(name, command, expected=None):
            return measure(machine + "/" + name, lambda: remote("alice", command, expected, machine=machine))

        for _ in range(3):
            sample("login", "echo ready", "ready")
            sample("eval-constant", "nix-instantiate --eval --expr 42", "42")
            sample("eval-packages", "nix-instantiate --eval --expr '(import <nix9>).stdenv.cc.name'", '"cc"')
            sample("source-import", "nix-store --add /n/projects/hello/hello.c")
            sample("query-profile", "nix-store -qR `{" + SCRIPT + "path}")
            result = sample("cached-build", "nix-build /n/projects/hello/environment.nix")
            if "building '" in result or "copying path" in result:
                raise RuntimeError(machine + ": warm build did not reuse the environment")
            sample("shell-startup", "cd /n/projects/hello && nix-shell --run 'echo ready'", "ready")
            sample("shell-compile", "cd /n/projects/hello && nix-shell --run '6c -o $home/hello.6 $src && "
                   "6l -o $home/hello $home/hello.6 && $home/hello'", HELLO)


def check_source_edits(remote, measure):
    original = "/usr/alice/hello-original.c"
    source = "/n/projects/hello/hello.c"
    remote("alice", f"cp {source} {original}")
    try:
        remote("alice", f"sed 's/shared workspace/edited workspace/' {original} > {source}")
        for machine in ("build", "batch"):
            result = measure(machine + "/source-edit-build", lambda: remote(
                "alice", "nix-build /n/projects/hello/environment.nix", machine=machine))
            environment = output_path(result)
            if "building '" not in result:
                raise RuntimeError(machine + ": changed source did not rebuild")
            remote("alice", ". " + environment + "/activate && hello",
                   "hello from the edited workspace", machine=machine)
    finally:
        remote("alice", f"cp {original} {source} && rm {original}")
    for machine in ("build", "batch"):
        result = measure(machine + "/restored-source-build", lambda: remote(
            "alice", "nix-build /n/projects/hello/environment.nix", machine=machine))
        if "building '" in result or "copying path" in result:
            raise RuntimeError(machine + ": restored source was not reused")
    print("PASS: shared source edits rebuild on both CPUs and restored sources reuse their environments", flush=True)
