"""Build and switch rooted environments using native namespace bindings."""

import re


def store_paths(result):
    return set(re.findall(r"/usr/local/nix/store/[a-z0-9]{32}-[A-Za-z0-9+._?=-]+", result))


def check_login(guest, packages, environments):
    root = "/usr/local/nix/state/gcroots/login-environment"
    guest.command("mkdir -p /tmp/nix9-login/lib")
    guest.command(f"echo '. {packages}/profile {root}' > /tmp/nix9-login/lib/profile")
    for name, message, present, absent in (
        ("one", "one", "old", "new"),
        ("two", "two", "new", "old"),
        ("one", "one", "old", "new"),
    ):
        guest.command(f"nix-store --realise --add-root {root} {environments[name]}")
        script = f"nix9-choice && nix9-{present}-only && test ! -e /bin/nix9-{absent}-only"
        guest.command(f"@{{ home=/tmp/nix9-login; rc -el -c '{script}' }}", message)
    # Reread the same profile in an existing shell after changing its root.
    guest.command(f". {packages}/profile {root}; nix9-choice", "one")
    guest.command(f"nix-store --realise --add-root {root} {environments['two']}")
    guest.command(f". {packages}/profile {root}; nix9-choice", "two")
    guest.command("test ! -e /bin/nix9-old-only")
    for contents in (None, "", "not-a-store-path", environments["one"] + " " + environments["two"]):
        if contents is None:
            argument = "/tmp/no-such-environment-root"
        else:
            guest.command(f"echo '{contents}' > /tmp/invalid-environment-root")
            argument = "/tmp/invalid-environment-root"
        result = guest.command(f". {packages}/profile {argument}; echo PROFILE-STATUS:$status")
        if not re.search(r"(?m)^PROFILE-STATUS:invalid environment root$", result):
            raise RuntimeError(f"invalid login root was not rejected: {result}")
        guest.command("nix9-choice", "two")
    result = guest.command(f". {packages}/profile; echo PROFILE-STATUS:$status")
    if not re.search(r"(?m)^PROFILE-STATUS:invalid environment root$", result):
        raise RuntimeError(f"missing login root argument was not rejected: {result}")
    guest.command(f". {environments['empty']}/activate")
    guest.command(f"rm {root}")


def check_configuration(guest, packages, port):
    guest.command(f"hget -o /tmp/environments.nix http://10.0.2.2:{port}/environments.nix")
    environments = {}
    for name in ("configured-one", "configured-two", "config-only", "missing-target", "empty"):
        root = f"/usr/local/nix/state/gcroots/{name}"
        guest.command(f"nix-build /tmp/environments.nix --argstr packages {packages} -A {name} --out-link {root}")
        environments[name] = store_paths(guest.command(f"cat {root}")).pop()
    guest.command("echo original > /tmp/nix9-config; echo original-extra > /tmp/nix9-extra")
    first, second = environments["configured-one"], environments["configured-two"]
    guest.command(f"@{{ . {first}/activate; cat /tmp/nix9-config }}", "one's config")
    guest.command("cat /tmp/nix9-config", "original")
    guest.command(f". {first}/activate; nix9-choice", "one")
    guest.command(f". {first}/activate; cat /tmp/nix9-extra", "extra")
    result = guest.command(f". {environments['missing-target']}/activate; echo CONFIG-STATUS:$status")
    if not re.search(r"(?m)^CONFIG-STATUS:.+$", result):
        raise RuntimeError(f"missing configuration target was not rejected: {result}")
    guest.command("nix9-choice", "one")
    guest.command("cat /tmp/nix9-config", "one's config")
    guest.command(f". {second}/activate; nix9-choice", "two")
    guest.command("echo -n two > /tmp/expected-config; cmp /tmp/expected-config /tmp/nix9-config")
    guest.command("cat /tmp/nix9-extra", "original-extra")
    guest.command("nix-store --gc")
    guest.command(f"nix-store --verify-path {first}")
    guest.command(f". {first}/activate; nix9-choice", "one")
    result = guest.command("cat /tmp/nix9-config")
    referenced = store_paths(result)
    if len(referenced) != 1:
        raise RuntimeError(f"configuration lost its package reference: {result}")
    data = referenced.pop()
    guest.command(f"cat {data}/share/message", "retained")
    guest.command(f". {environments['config-only']}/activate")
    guest.command("cat /tmp/nix9-config", "configuration without packages")
    guest.command("test ! -e /bin/nix9-choice")
    guest.command(f". {environments['empty']}/activate")
    guest.command("cat /tmp/nix9-config", "original")
    guest.command("cat /tmp/nix9-extra", "original-extra")
    for name in environments:
        guest.command(f"rm /usr/local/nix/state/gcroots/{name}")
    guest.command("nix-store --gc")
    guest.command(f"test ! -e {first} && test ! -e {data}")


def check_generations(guest, packages, environments):
    root = "/usr/local/nix/state/gcroots/profile-test"
    guest.command(f"fn profileTest {{ {packages}/bin/nix-profile {root} $* }}")
    command = "profileTest"
    first, second = environments["one"], environments["two"]
    guest.command(f"{command} set {first}")
    guest.command(f"cat {root}.generations/1", first)
    guest.command(f"rm {root} {root}.generations/1 {root}.generations")
    # Adopting an existing login root must preserve its old environment.
    guest.command(f"nix-store --realise --add-root {root} {first}")
    guest.command(f"{command} set {second}")
    result = guest.command(f"{command} list")
    for number, marker, path in ((1, "", first), (2, r"\*", second)):
        if not re.search(rf"(?m)^{number}\s+{marker}\s*{re.escape(path)}$", result):
            raise RuntimeError(f"missing profile generation: {result}")
    guest.command("nix-store --gc")
    guest.command(f"nix-store --verify-path {first} {second}")
    guest.command(f"{command} rollback")
    guest.command(f". {packages}/profile {root} && nix9-choice", "one")
    # Selecting a retained environment reuses its generation.
    guest.command(f"{command} set {second} && {command} set {second}")
    guest.command(f"test ! -e {root}.generations/3")
    guest.command(f". {packages}/profile {root} && nix9-choice", "two")
    guest.command("mkdir -p /tmp/not-a-store-environment; touch /tmp/not-a-store-environment/activate")
    for arguments in (
        "delete 2", "delete ../profile-test", "set /tmp/no-environment",
        "set /tmp/not-a-store-environment", "unknown",
    ):
        result = guest.command(f"{command} {arguments}; echo PROFILE-ERROR:$status")
        if not re.search(r"(?m)^PROFILE-ERROR:.+$", result):
            raise RuntimeError(f"invalid profile operation succeeded: {result}")
        guest.command(f"cat {root}", second)
        guest.command("test ! -e '#s/nix9-profile'")
    guest.command("@{ status='' } > '#s/nix9-profile'")
    result = guest.command(f"{command} rollback; echo PROFILE-ERROR:$status")
    if "profiles are locked" not in result or not re.search(r"(?m)^PROFILE-ERROR:.+$", result):
        raise RuntimeError(f"concurrent profile operation was not rejected: {result}")
    guest.command("rm '#s/nix9-profile'")
    guest.command(f"{command} delete 1")
    guest.command("nix-store --gc")
    guest.command(f"test ! -e {first} && nix-store --verify-path {second}")
    result = guest.command(f"{command} rollback; echo PROFILE-ERROR:$status")
    if "no previous generation" not in result or not re.search(r"(?m)^PROFILE-ERROR:.+$", result):
        raise RuntimeError(f"rollback without a generation succeeded: {result}")
    guest.command(f". {environments['empty']}/activate")
    guest.command(f"rm {root} {root}.generations/2 {root}.generations")


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
    check_login(guest, packages, environments)
    for name in environments:
        if name != "empty":
            guest.command(f"rm /usr/local/nix/state/gcroots/environment-{name}")
    check_generations(guest, packages, environments)
    guest.command("rm /usr/local/nix/state/gcroots/environment-empty")
    guest.command("nix-store --gc")
    guest.command(f"test ! -e {environments['one']} && test ! -e {environments['two']}")
    for package in selected:
        guest.command(f"test ! -e {package}")
    check_configuration(guest, packages, port)
    return "native buildEnv, configuration files, login, profile generations, rollback, closure retention and GC passed"
