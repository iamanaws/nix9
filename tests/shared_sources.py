"""Shared source reuse still observes content, filters, modes and collection."""

import re


def check_sources(guest, user_command, until, clean_builds):
    def quote(value):
        return "'" + value.replace("'", "''") + "'"

    def expression(user="alice", *, recursive=True, expected_hash=None):
        return ('builtins.path { name = "shared-source"; path = /usr/' + user
                      + '/import-source' + ('' if recursive else '/kept') + '; '
                      + ('filter = path: type: builtins.baseNameOf path != "ignored"; '
                         if recursive else 'recursive = false; ')
                      + (f'sha256 = "{expected_hash}"; ' if expected_hash else '') + '}')

    def import_source(user="alice", *, recursive=True, repair=False, expected_hash=None):
        command = "nix-instantiate --eval --read-write-mode --expr " + quote(
            expression(user, recursive=recursive, expected_hash=expected_hash))
        if repair:
            command += " --repair"
        result = user_command(user, command)
        paths = re.findall(r'(?m)^"(/usr/local/nix/store/[^\s"]+)"$', result)
        if len(paths) != 1:
            raise RuntimeError("expected one imported source: " + result)
        return paths[0]

    def override():
        result = user_command("alice", "nix-instantiate --eval --read-write-mode --expr " + quote(
            '((import <nix9>).fortune.override { src = /usr/alice/import-source; }).drvPath'))
        paths = re.findall(r'(?m)^"(/usr/local/nix/store/[^\s"]+\.drv)"$', result)
        if len(paths) != 1:
            raise RuntimeError("expected one overridden derivation: " + result)
        return paths[0]

    for user in ("alice", "bob"):
        user_command(user, "mkdir -p $home/import-source && "
                     "echo -n first > $home/import-source/kept && "
                     "echo ignored > $home/import-source/ignored && chmod 644 $home/import-source/kept")
    first = import_source()
    if import_source() != first or import_source("bob") != first:
        raise RuntimeError("identical sources did not reuse one shared path")
    guest.command("cat " + first + "/kept; echo", "first")
    guest.command("test ! -e " + first + "/ignored")
    result = user_command("alice", "nix-store -q --hash " + first)
    source_hash = re.findall(r"(?m)^(sha256:\S+)$", result)
    if len(source_hash) != 1:
        raise RuntimeError("expected one source hash: " + result)
    source_hash = source_hash[0]
    if import_source(expected_hash=source_hash) != first:
        raise RuntimeError("a fixed input changed the source path")
    original_override = override()
    user_command("alice", "echo changed > $home/import-source/ignored")
    if import_source() != first:
        raise RuntimeError("an excluded file changed the source path")
    ignored_override = override()
    # Equal length, no timestamp delay: reuse must depend on content.
    user_command("alice", "echo -n other > $home/import-source/kept")
    edited = import_source()
    if edited == first:
        raise RuntimeError("a same-size source edit was missed")
    if override() == ignored_override:
        raise RuntimeError("a package source override missed an edit")
    guest.command("cat " + edited + "/kept; echo", "other")
    user_command("alice", "echo -n first > $home/import-source/kept")
    if import_source() != first:
        raise RuntimeError("restored source did not reuse its original path")
    # The unfiltered override also includes the edited ignored file.
    user_command("alice", "echo ignored > $home/import-source/ignored")
    if override() != original_override:
        raise RuntimeError("restored override did not reuse its original derivation")
    flat = import_source(recursive=False)
    user_command("alice", "chmod 755 $home/import-source/kept")
    executable = import_source()
    if executable == first or import_source(recursive=False) != flat:
        raise RuntimeError("recursive and flat imports mishandled the executable bit")
    guest.command("chmod 755 " + executable + "/kept && echo damaged > " + executable + "/kept")
    if import_source(repair=True) != executable:
        raise RuntimeError("source repair changed the store path")
    guest.command("nix-store --verify-path " + executable)
    guest.command("cat " + executable + "/kept; echo", "first")
    user_command("alice", "chmod 644 $home/import-source/kept")
    root = "/usr/local/nix/state/gcroots/per-user/alice/import-source"
    user_command("alice", "nix-store --realise " + first + " --add-root " + root)
    clean_builds()
    guest.command("nix-store --gc")
    guest.command("nix-store --verify-path " + first)
    user_command("alice", "nix-store --delete-root " + root)
    clean_builds()
    guest.command("nix-store --gc && test ! -e " + first)
    if import_source(expected_hash=source_hash) != first:
        raise RuntimeError("a collected source was not restored at the same path")
    guest.command("nix-store --verify-path " + first)
    clean_builds()

    # An unrelated build holds evaluation open without rooting the source itself.
    # Native GC requires exclusive access while evaluation uses cached inputs.
    waiting = ('let source = ' + expression(expected_hash=source_hash) + '; blocker = derivation { '
               'name = "shared-source-gc-blocker"; system = "x86_64-plan9"; builder = "/bin/rc"; '
               'args = [ "-e" "-c" "/bin/echo SOURCE-WAITING; '
               'while(! /bin/test -e /usr/shared-source-release) /bin/sleep 1; /bin/echo done > $out" ]; }; '
               'in builtins.seq source (builtins.seq (builtins.readFile blocker) '
               '(builtins.readFile (source + "/kept")))')
    user_command("alice", "echo " + quote(waiting) + " > $home/source-gc.nix")
    guest.command("@{ as alice 'nix-instantiate --eval --read-write-mode $home/source-gc.nix' "
                  ">/tmp/source-gc.log >[2=1]; echo $status >/tmp/source-gc.status } &")
    try:
        until("grep -s '^SOURCE-WAITING$' /tmp/source-gc.log", "fixed-input evaluation", timeout=90)
        guest.command("test ! -e /tmp/source-gc.status")
        result = guest.command("nix-store --gc; echo SOURCE-GC-ERROR:$status")
        if "exclusive store access required" not in result or not re.search(r"(?m)^SOURCE-GC-ERROR:.+", result):
            raise RuntimeError("GC did not protect the active evaluator: " + result)
    finally:
        guest.command("echo release > /usr/shared-source-release; chmod 644 /usr/shared-source-release")
    until("test -f /tmp/source-gc.status", "fixed-input evaluator exit")
    guest.command("test `{wc -c </tmp/source-gc.status} -eq 1 && grep '^\"first\"$' /tmp/source-gc.log", '"first"')
    clean_builds()
    guest.command("nix-store --gc && test ! -e " + first)
    guest.command("rm /usr/shared-source-release")
    print("PASS: shared source reuse preserves edits, filters, executable bits, repair and GC", flush=True)
