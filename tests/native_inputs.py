"""Check build tools and native/APE library discovery without namespace leaks."""

import re


def check_shell(guest, packages, port):
    guest.command(f"hget -o /tmp/inputs.nix http://10.0.2.2:{port}/inputs.nix")
    guest.command(f"shellPackages={packages}")
    guest.command("fn shellBuild { nix-build /tmp/inputs.nix --argstr packages $shellPackages -A $1 --out-link $2 }")
    root = "/usr/local/nix/state/gcroots/development-shell"
    guest.command(f"shellBuild shell {root}")
    guest.command(f"developmentShell=`{{cat {root}}}")
    guest.command("nix-store --gc; nix-store --verify-path $developmentShell")
    guest.command("mkdir /tmp/shell-project; cd /tmp/shell-project")
    guest.command("outsidePath=$path; outsidePATH=$PATH")
    guest.child.sendline("$developmentShell/shell; echo NIX9-SHELL-EXIT:$status")
    guest.child.expect(r"(?m)^NIX9-SHELL-READY\r*$")
    guest.child.expect(r"(?m)^term% ")
    guest.command("echo $NIX9_SHELL_TEST", "ready")
    guest.command("test ! -e /bin/input-only && test ! -e /sys/include/build-tool-only.h")
    guest.command("generate > generated.h")
    guest.command("6c -I . -o main.6 $shellSource; 6l -s -o answer main.6; ./answer", "native inputs PASS")
    guest.command("pcc -I . -o ape-answer $apeShellSource -lanswer; ./ape-answer", "ape inputs PASS")
    guest.command("./ape-answer tool > generated-from-ape.h; cat generated-from-ape.h", "#define BUILD_NUMBER 42")
    guest.command("test -e /no-such-shell-command; echo interactive-shell-alive", "interactive-shell-alive")
    guest.child.sendline("exit")
    guest.child.expect(r"(?m)^NIX9-SHELL-EXIT:\r*$")
    guest.child.expect(r"(?m)^term% ")
    guest.command("test ! -e /bin/generate && test ! -e /sys/include/answer.h")
    guest.command("test ! -e /sys/include/ape/answer.h && test ! -e /amd64/lib/libanswer.a")
    guest.command("test ! -e /amd64/lib/ape/libanswer.a && ~ $#NIX9_SHELL_TEST 0")
    for variable, original in (("path", "outsidePath"), ("PATH", "outsidePATH")):
        result = guest.command(f"echo ${variable}; echo ${original}")
        lines = [line for line in result.splitlines() if line.startswith("/")]
        if len(lines) != 2 or lines[0] != lines[1]:
            raise RuntimeError(f"development shell changed {variable}: {result}")
    guest.command("$developmentShell/shell -c 'generate'", "#define BUILD_NUMBER 42")
    guest.command(f"shellBuild failedShell {root}")
    guest.command(f"failedShell=`{{cat {root}}}")
    result = guest.command("$failedShell/shell -c 'echo unexpected-shell-command'; echo SHELL-STATUS:$status")
    if not re.search(r"(?m)^SHELL-STATUS:.+$", result) or re.search(r"(?m)^unexpected-shell-command$", result):
        raise RuntimeError(f"shell hook failure did not stop entry: {result}")
    guest.command(f"rm {root}; cd /")
    return "interactive native/APE builds, inputs, shellHook, command mode, GC and namespace restoration passed"


def check_inputs(guest, packages, port):
    guest.command(f"hget -o /tmp/inputs.nix http://10.0.2.2:{port}/inputs.nix")
    guest.command(f"inputPackages={packages}")
    guest.command("fn inputs { nix-build /tmp/inputs.nix --argstr packages $inputPackages -A $1 --out-link $2 }")
    outputs = {}
    for kind in ("native", "ape"):
        root = f"/usr/local/nix/state/gcroots/{kind}-inputs"
        guest.command(f"inputs {kind} {root}")
        result = guest.command(f"cat {root}")
        paths = re.findall(rf"(?m)^/usr/local/nix/store/[a-z0-9]{{32}}-{kind}-inputs$", result)
        if len(paths) != 1:
            raise RuntimeError(f"missing {kind} input test output: {result}")
        outputs[kind] = paths[0]
    result = guest.command(f"nix-store -qR {outputs['native']}")
    closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result))
    if closure != {outputs["native"]}:
        raise RuntimeError(f"static native program retains build dependencies: {closure}")
    guest.command("test ! -e /sys/include/answer.h && test ! -e /sys/include/ape/answer.h")
    guest.command("test ! -e /amd64/lib/libanswer.a && test ! -e /amd64/lib/ape/libanswer.a")
    guest.command("nix-store --gc")
    for kind, package in outputs.items():
        guest.command(f"{package}/bin/answer", f"{kind} inputs PASS")
        guest.command(f"nix-store --verify-path {package}")
        guest.command(f"rm /usr/local/nix/state/gcroots/{kind}-inputs")
    return "build tools, POSIX PATH, separate native/APE headers and libraries, namespace isolation and GC passed"
