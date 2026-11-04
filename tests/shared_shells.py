"""User shells retain dependencies without keeping a store worker alive."""

import re


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def check_shells(guest, user_command, rejected, until, clean_builds):
    base = "/usr/local/nix/state/gcroots/per-user/"
    enter = "nix-shell /usr/shared-store.nix -A shellPackage"

    def idle_store():
        until("test `{ls /usr/local/nix/state/db/clients | wc -l} -eq 0", "shell store connection close")
        until("test `{ps | grep ' nix-store-service$' | wc -l} -eq 1", "shell connection helper exit")

    def no_roots(user):
        until("test ! -e " + base + user + "/nix-shell-*", user + " shell root cleanup")

    def live_root(user):
        result = guest.command("ls " + base + user + "/nix-shell-*")
        roots = re.findall(r"(?m)^" + re.escape(base + user) + r"/nix-shell-\S+$", result)
        if len(roots) != 1:
            raise RuntimeError("expected one shell root: " + result)
        result = guest.command("cat " + roots[0])
        targets = re.findall(r"(?m)^/usr/local/nix/store/\S+$", result)
        if len(targets) != 1:
            raise RuntimeError("invalid shell root: " + result)
        return roots[0], targets[0]

    for user in ("alice", "bob"):
        user_command(user, "mkdir -p $home/project; cd $home/project")
        for flags in ("", "--pure --keep SHELL_KEEP"):
            command = ("flag e +; ~ `{cat /dev/user} " + user + "; ~ $sharedShellHook ready; "
                       "~ $SHELL_KEEP 'kept value'; cat $messagePath; echo SHELL-TEMP:$TMPDIR; "
                       "6c -o hello.6 $src; 6l -o hello hello.6; ./hello; "
                       "test ! -w /usr/local/nix/store; test ! -w /usr/local/nix/state/db/db.sqlite; ")
            if flags:
                command += "~ $IN_NIX_SHELL pure; ~ $#SHELL_DROP 0"
            else:
                command += "~ $IN_NIX_SHELL impure; ~ $SHELL_DROP inherited"
            result = user_command(user, "cd $home/project; SHELL_KEEP='kept value'; SHELL_DROP=inherited; "
                                  + enter + " " + flags + " --run " + quote(command))
            if "a shell's message\nsecond line\n" not in result or "shared shell C PASS\n" not in result:
                raise RuntimeError("shell environment or compilation failed: " + result)
            temporary = re.findall(r"(?m)^SHELL-TEMP:(/\S+)$", result)
            if len(temporary) != 1:
                raise RuntimeError("missing shell temporary directory: " + result)
            user_command(user, "test ! -e " + temporary[0])
            no_roots(user)
        rejected(user, enter + " --run 'exit shell-command-failed'", "shell-command-failed")
        rejected(user, "nix-shell /usr/shared-store.nix -A failedShell --run 'echo UNEXPECTED-SHELL'",
                 "intentional shell hook failure")
        no_roots(user)
    clean_builds()

    # Exercise the actual interactive entry point with a distinct prompt.
    guest.child.sendline("as alice " + quote("prompt=('shared% ' ' '); cd $home/project; "
                         "nix-shell /usr/shared-store.nix -A shell") + "; echo SHARED-SHELL-EXIT:$status")
    guest.child.expect(r"(?m)^SHARED-SHELL-READY\r*$")
    guest.child.expect(r"(?m)^shared% ")
    original_prompt = guest.prompt
    guest.prompt = r"(?m)^shared% "
    guest.command("echo `{cat /dev/user}", "alice")
    guest.command("~ $IN_NIX_SHELL impure && echo interactive > $home/project/interactive && rm $home/project/interactive")
    guest.child.sendline("exit")
    guest.child.expect(r"(?m)^SHARED-SHELL-EXIT:\r*$")
    guest.child.expect(original_prompt)
    guest.prompt = original_prompt
    no_roots("alice")
    clean_builds()

    def start(user, name, mode="hold"):
        directory = f"/usr/{user}/shell-{name}"
        user_command(user, "mkdir " + directory)
        guest.command("@{ as " + user + " '. /usr/shared-shell.rc " + directory + " " + mode
                      + "' >/tmp/shell-" + name + ".log >[2=1]; "
                      "echo $status >/tmp/shell-" + name + ".status } &")
        try:
            until("test -f " + directory + "/pid", name + " shell child", timeout=90)
        except Exception:
            guest.command("cat /tmp/shell-" + name + ".log")
            raise
        return directory

    def ended(name, success=True):
        until("test -f /tmp/shell-" + name + ".status", name + " shell exit")
        guest.command("test `{wc -c </tmp/shell-" + name + ".status} " + ("-eq" if success else "-gt") + " 1")

    # Both users hold roots, but neither holds a store connection or database lock.
    active = {user: start(user, user) for user in ("alice", "bob")}
    roots = {user: live_root(user) for user in active}
    idle_store()
    guest.command("nix-store --gc")
    for user, (root, target) in roots.items():
        guest.command("test -e " + root + "; nix-store --verify-path " + target)
        user_command(user, "test ! -w " + root)
    for user, directory in active.items():
        user_command(user, "echo stop > " + directory + "/stop")
        ended(user)
        no_roots(user)
    clean_builds()
    guest.command("nix-store --gc")
    for _, target in roots.values():
        guest.command("test ! -e " + target)

    for name, mode in (("interrupt", "hold"), ("killed-parent", "hold"), ("detached", "detach")):
        directory = start("alice", name, mode)
        root, target = live_root("alice")
        idle_store()
        if name == "interrupt":
            user_command("alice", "echo interrupt > /proc/`{cat " + directory + "/pid}^/note")
            ended(name, success=False)
        else:
            if name == "killed-parent":
                # rc defers a kill note while waiting for its child. The ctl
                # operation kills the launcher immediately, leaving that child.
                user_command("alice", "echo kill > /proc/`{cat " + directory + "/launcher.pid}^/ctl")
                until("test ! -d /proc/`{cat " + directory + "/launcher.pid}", "launcher death")
            ended(name, success=name == "detached")
            # A surviving descendant still needs the closure after its shell exits.
            guest.command("nix-store --gc; test -e " + root + "; nix-store --verify-path " + target)
            user_command("alice", "echo stop > " + directory + "/stop")
        no_roots("alice")
        clean_builds()
        guest.command("nix-store --gc; test ! -e " + target)
    print("PASS: shared shells, caller identity, native C, pure environments, hooks, GC and descendant lifetime", flush=True)
