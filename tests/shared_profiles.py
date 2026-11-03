"""Persistent roots and profile generations through the authenticated store."""

import re


def check_profiles(guest, user_command, rejected, clean_builds):
    base = "/usr/local/nix/state/gcroots"
    roots = {user: base + "/per-user/" + user for user in ("alice", "bob")}

    def run(user, command):
        # Discover the authenticated root directory on each fresh connection.
        return user_command(user, "r=`{nix-store --roots-dir}; " + command)

    def environment(user, attribute, flags=""):
        result = run(user, "nix-build /usr/shared-store.nix -A " + attribute + " " + flags)
        paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
        if len(paths) != 1:
            raise RuntimeError("missing environment result: " + result)
        return paths[0], result

    for user in roots:
        result = user_command(user, "nix-store --roots-dir")
        if not re.search(r"(?m)^" + re.escape(roots[user]) + "$", result):
            raise RuntimeError("wrong authenticated roots: " + result)
    first, _ = environment("alice", "envOne")
    reused, log = environment("bob", "envOne")
    if reused != first or "building '" in log:
        raise RuntimeError("Bob did not reuse Alice's environment: " + log)
    for user in roots:
        guest.command("cat " + roots[user] + "/result", first)
        run(user, "nix-profile $r/environment set `{cat $r/result}")
        result = run(user, ". $nix9/packages/profile $r/environment; shared-choice")
        if not re.search(r"(?m)^one$", result):
            raise RuntimeError("environment activation failed: " + result)
        run(user, "nix-store --delete-root $r/result")

    second, _ = environment("alice", "envTwo", "--out-link `{nix-store --roots-dir}^/candidate")
    run("alice", "nix-profile $r/environment set `{cat $r/candidate}; nix-store --delete-root $r/candidate")
    guest.command("cat " + roots["bob"] + "/environment", first)
    guest.command("cat " + roots["alice"] + "/environment", second)
    for action in ("rollback", "set " + second, "set " + second, "rollback"):
        run("alice", "nix-profile $r/environment " + action)
    guest.command("cat " + roots["alice"] + "/environment", first)
    listing = run("alice", "nix-profile $r/environment list")
    if not re.search(r"(?m)^1 \* " + re.escape(first) + "$", listing) or not re.search(
            r"(?m)^2\s+" + re.escape(second) + "$", listing):
        raise RuntimeError("wrong profile history: " + listing)
    guest.command("test ! -e " + roots["alice"] + "/environment.generations/3")

    # The server checks identity even for raw root operations and forged $user.
    bob = roots["bob"] + "/environment"
    for root in (bob, base + "/system", roots["alice"] + "/../bob/environment"):
        rejected("alice", "nix-store --realise " + first + " --add-root " + root, "root access denied")
        rejected("alice", "nix-store --delete-root " + root, "root access denied")
    rejected("alice", "user=bob; nix-profile " + bob + " set " + second, "root access denied")
    rejected("alice", "nix-profile " + roots["alice"] + "/environment delete 1", "current generation")
    rejected("alice", "nix-profile " + roots["alice"] + "/environment delete ../environment", "unknown generation")
    for user in roots:
        run(user, "test ! -w $r && test ! -w $r/environment && test ! -w $r/environment.generations")
    guest.command("cat " + bob, first)

    # Two sessions updating one profile must preserve both generations.
    guest.command("one=" + first + "; two=" + second)
    guest.command("race=" + roots["alice"] + "/race")
    guest.command("fn raceProfile { as alice 'nix-profile '^$race^' set '^$1; echo $status > /tmp/race-$2 }")
    guest.command("@{ @{ raceProfile $one one > /tmp/race-one.log >[2=1] } & @{ raceProfile $two two > /tmp/race-two.log >[2=1] } & wait }")
    guest.command("test `{wc -c < /tmp/race-one} -eq 1 && test `{wc -c < /tmp/race-two} -eq 1")
    listing = run("alice", "nix-profile $r/race list")
    for path in (first, second):
        if not re.search(r"(?m)^[12]\s+\*?\s*" + re.escape(path) + "$", listing):
            raise RuntimeError("concurrent profile update lost a generation: " + listing)
    run("alice", "for(f in $r/race.generations/* $r/race) nix-store --delete-root $f")

    clean_builds()
    guest.command("nix-store --gc")
    guest.command("nix-store --verify-path " + first + " " + second)
    # Alice releases her older selection; Bob's independent generation keeps it.
    run("alice", "nix-profile $r/environment set " + second)
    run("alice", "nix-profile $r/environment delete 1")
    clean_builds()
    guest.command("nix-store --gc; test -e " + first)
    run("bob", "nix-profile $r/environment set " + second)
    run("bob", "nix-profile $r/environment delete 1")
    clean_builds()
    guest.command("nix-store --gc")
    guest.command("test ! -e " + first + " && nix-store --verify-path " + second)
    for user in roots:
        result = run(user, ". $nix9/packages/profile $r/environment; shared-choice")
        if not re.search(r"(?m)^two$", result):
            raise RuntimeError("retained environment stopped working: " + result)
    clean_builds()
    print("PASS: shared roots, independent generations, rollback, concurrent updates, ownership and GC", flush=True)
