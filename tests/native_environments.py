"""Build and switch rooted environments using native namespace bindings."""

import re


def store_paths(result):
    return set(re.findall(r"/usr/local/nix/store/[a-z0-9]{32}-[A-Za-z0-9+._?=-]+", result))


def check_environments(guest, packages, port):
    guest.command(f"hget -o /tmp/environments.nix http://10.0.2.2:{port}/environments.nix")
    guest.command(f"environmentPackages={packages}")
    guest.command("fn environment { nix-build /tmp/environments.nix --argstr packages $environmentPackages -A $1 --out-link $2 }")
    environments = {}
    for name in ("one", "two", "empty", "duplicate", "tools"):
        root = f"/usr/local/nix/state/gcroots/environment-{name}"
        guest.command(f"environment {name} {root}")
        paths = store_paths(guest.command(f"cat {root}"))
        if len(paths) != 1:
            raise RuntimeError(f"missing {name} environment: {paths}")
        environments[name] = paths.pop()
    result = guest.command("environment collision /usr/local/nix/state/gcroots/collision; echo COLLISION-STATUS:$status")
    if "command collision: nix9-choice" not in result or not re.search(r"(?m)^COLLISION-STATUS:.*cc9exit=100$", result):
        raise RuntimeError(f"command collision was not rejected: {result}")
    guest.command("test ! -e /usr/local/nix/state/gcroots/collision")
    guest.command("basePath=$path; basePATH=$PATH")
    guest.command(f"@{{ . {environments['one']}/activate; nix9-choice }}", "one")
    guest.command("test ! -e /bin/nix9-choice")
    guest.command(f". {environments['one']}/activate; nix9-choice", "one")
    guest.command(f". {environments['one']}/activate; nix9-choice", "one")
    guest.command("nix9-old-only", "old-only")
    guest.command("test ! -e /bin/nix9-new-only")
    selected = store_paths(guest.command("echo $nix9EnvironmentPaths"))
    closure = store_paths(guest.command(f"nix-store -qR {environments['one']}"))
    if closure != selected | {environments["one"]} or len(selected) != 3:
        raise RuntimeError(f"environment does not retain exactly its selected packages: {closure}")
    guest.command(f". {environments['two']}/activate; nix9-choice", "two")
    guest.command("nix9-new-only", "new-only")
    guest.command("test ! -e /bin/nix9-old-only")
    for variable in ("path", "PATH"):
        result = guest.command(f"echo ${variable}")
        if any(package + "/bin" in result for package in selected):
            raise RuntimeError(f"old commands remain in {variable}: {result}")
    guest.command("nix-store --gc")
    guest.command(f"nix-store --verify-path {environments['one']} {environments['two']}")
    guest.command(f". {environments['one']}/activate; nix9-choice", "one")
    guest.command("test ! -e /bin/nix9-new-only")
    guest.command(f". {environments['tools']}/activate")
    guest.command("test ! -e /bin/nix9-choice && test ! -e /bin/nix9-old-only")
    guest.command("lua -e 'print(6 * 7)'", "42")
    guest.command("fortune > /tmp/environment-fortune; test -s /tmp/environment-fortune")
    guest.command(f". {environments['empty']}/activate")
    guest.command("test ! -e /bin/nix9-choice && test ! -e /bin/nix9-new-only")
    for variable, original in (("path", "basePath"), ("PATH", "basePATH")):
        result = guest.command(f"echo ${variable}; echo ${original}")
        lines = [line for line in result.splitlines() if line.startswith("/")]
        if len(lines) != 2 or lines[0] != lines[1]:
            raise RuntimeError(f"{variable} was not restored: {result}")
    for name in environments:
        guest.command(f"rm /usr/local/nix/state/gcroots/environment-{name}")
    guest.command("nix-store --gc")
    guest.command(f"test ! -e {environments['one']} && test ! -e {environments['two']}")
    for package in selected:
        guest.command(f"test ! -e {package}")
    return "native buildEnv, collisions, private activation, switching, rollback, closure retention and GC passed"
