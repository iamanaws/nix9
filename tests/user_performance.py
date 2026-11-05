"""Measure development commands with fresh logins and an existing CPU session."""

from contextlib import contextmanager

from guest import Guest
from user_development import output_path


@contextmanager
def cpu_session(auth, machine):
    prompt = r"(?m)^nix9-benchmark% "
    command = "prompt=('nix9-benchmark% ' ' '); exec /bin/rc -i"
    quoted = "'" + command.replace("'", "''") + "'"
    auth.child.sendline("rcpu -u alice -h " + machine + " -c " + quoted
                        + "; echo NIX9-SESSION-EXIT:$status")
    auth.child.expect(prompt)
    session = Guest(auth.child, prompt)
    try:
        session.command("echo `{cat /dev/user}", "alice")
        yield session
    finally:
        auth.child.sendline("exit")
        auth.child.expect(r"(?m)^NIX9-SESSION-EXIT:([^\n]*)\n")
        status = auth.child.match.group(1).strip()
        auth.child.expect(auth.prompt)
        if status:
            raise RuntimeError("CPU benchmark session failed: " + status)


def benchmark_commands(run, measure, prefix):
    # GC in the functional suite may have removed build inputs. Restore these
    # separately so all repeated shell samples describe a warm environment.
    shell = "cd /n/projects/hello && nix-shell --run "
    measure(prefix + "/warmup-shell", lambda: run(shell + "'echo ready'", "ready"))
    derivation = output_path(run("nix-instantiate /n/projects/hello/environment.nix", None))
    commands = (
        ("ready", "echo ready", "ready"),
        ("version", "nix-instantiate --version", None),
        ("eval-constant", "nix-instantiate --eval --expr 42", "42"),
        ("eval-packages", "nix-instantiate --eval --expr '(import <nix9>).stdenv.cc.name'", '"cc"'),
        ("instantiate-project", "nix-instantiate /n/projects/hello/environment.nix", None),
        ("realise-project", "nix-store --realise " + derivation, None),
        ("source-import", "nix-store --add /n/projects/hello/hello.c", None),
        ("query-profile", "nix-store -qR `{rc /usr/user-development.rc path}", None),
        ("cached-build", "nix-build /n/projects/hello/environment.nix", None),
        ("shell-startup", shell + "'echo ready'", "ready"),
        ("shell-compile", shell + "'6c -o $home/hello.6 $src && "
         "6l -o $home/hello $home/hello.6 && $home/hello'", "hello from the shared workspace"),
    )
    for _ in range(3):
        for name, command, expected in commands:
            result = measure(prefix + "/" + name, lambda: run(command, expected))
            if name in ("realise-project", "cached-build") and ("building '" in result or "copying path" in result):
                raise RuntimeError(prefix + ": warm build did not reuse the environment")


def benchmark_development(auth, remote, measure):
    for machine in ("build", "batch"):
        benchmark_commands(lambda command, expected: remote("alice", command, expected, machine=machine),
                           measure, machine + "/login")
        with cpu_session(auth, machine) as session:
            benchmark_commands(session.command, measure, machine + "/session")
