"""Check build tools and native/APE library discovery without namespace leaks."""

import re


def check_shell(guest, packages, port):
    guest.command("nix-store --gc")
    guest.command(f"hget -o /tmp/inputs.nix http://10.0.2.2:{port}/inputs.nix")
    guest.command(f"shellPackages={packages}")
    guest.command("mkdir /tmp/shell-project; cp /tmp/inputs.nix /tmp/shell-project/shell.nix; cd /tmp/shell-project")
    guest.command("fn shellEnter { nix-shell --argstr packages $shellPackages -A $1 $*(2-) }")
    guest.command("outsidePath=$path; outsidePATH=$PATH")
    guest.child.sendline("shellEnter shell; echo NIX9-SHELL-EXIT:$status")
    guest.child.expect(r"(?m)^NIX9-SHELL-READY\r*$")
    guest.child.expect(r"(?m)^term% ")
    guest.command("echo $NIX9_SHELL_TEST", "ready")
    guest.command("echo $IN_NIX_SHELL", "impure")
    result = guest.command("ls /usr/local/nix/state/gcroots/nix-shell-*")
    roots = re.findall(r"(?m)^/usr/local/nix/state/gcroots/nix-shell-[^\s]+$", result)
    if len(roots) != 1:
        raise RuntimeError(f"missing live shell root: {result}")
    guest.command(f"developmentShell=`{{cat {roots[0]}}}")
    guest.command("nix-store --gc && nix-store --verify-path $developmentShell")
    guest.command("test ! -e /bin/input-only && test ! -e /sys/include/build-tool-only.h")
    guest.command("generate > generated.h")
    guest.command("6c -I . -o main.6 $shellSource; 6l -s -o answer main.6; ./answer", "native inputs PASS")
    guest.command("pcc -I . -o ape-answer $apeShellSource -lanswer; ./ape-answer", "ape inputs PASS")
    guest.command("./ape-answer tool > generated-from-ape.h; cat generated-from-ape.h", "#define BUILD_NUMBER 42")
    guest.command("test -e /no-such-shell-command; echo interactive-shell-alive", "interactive-shell-alive")
    guest.child.sendline("exit")
    guest.child.expect(r"(?m)^NIX9-SHELL-EXIT:\r*$")
    guest.child.expect(r"(?m)^term% ")
    # The kernel can finish remove-on-close work after the process exits.
    guest.command(f"for(i in 1 2 3 4 5) {{ if(test -e {roots[0]}) sleep 1 }}; test ! -e {roots[0]}")
    guest.command("~ $#IN_NIX_SHELL 0")
    guest.command("test ! -e /bin/generate && test ! -e /sys/include/answer.h")
    guest.command("test ! -e /sys/include/ape/answer.h && test ! -e /amd64/lib/libanswer.a")
    guest.command("test ! -e /amd64/lib/ape/libanswer.a && ~ $#NIX9_SHELL_TEST 0")
    for variable, original in (("path", "outsidePath"), ("PATH", "outsidePATH")):
        result = guest.command(f"echo ${variable}; echo ${original}")
        lines = [line for line in result.splitlines() if line.startswith("/")]
        if len(lines) != 2 or lines[0] != lines[1]:
            raise RuntimeError(f"development shell changed {variable}: {result}")
    guest.command("nix-shell /tmp/inputs.nix --argstr packages $shellPackages -A shell --run 'generate'", "#define BUILD_NUMBER 42")
    guest.command("shellEnter shell --run ''")
    result = guest.command("shellEnter shell --run 'exit shell-command-failed'; echo SHELL-STATUS:$status")
    if not re.search(r"(?m)^SHELL-STATUS:.*shell-command-failed$", result):
        raise RuntimeError(f"shell command lost its exit status: {result}")
    result = guest.command("shellEnter shell --run 'echo kill > /proc/$pid/note'; echo SHELL-STATUS:$status")
    if not re.search(r"(?m)^SHELL-STATUS:.+$", result):
        raise RuntimeError(f"killed shell reported success: {result}")
    result = guest.command("shellEnter failedShell --run 'echo unexpected-shell-command'; echo SHELL-STATUS:$status")
    if not re.search(r"(?m)^SHELL-STATUS:.+$", result) or re.search(r"(?m)^unexpected-shell-command$", result):
        raise RuntimeError(f"shell hook failure did not stop entry: {result}")
    for flag in ("--pure", "-p", "--out-link /tmp/shell-root"):
        result = guest.command(f"nix-shell {flag}; echo SHELL-STATUS:$status")
        if not re.search(r"(?m)^SHELL-STATUS:.+$", result):
            raise RuntimeError(f"unsupported shell option accepted: {result}")
    guest.command("for(i in 1 2 3 4 5) { if(test -e /usr/local/nix/state/gcroots/nix-shell-*) sleep 1 }; test ! -e /usr/local/nix/state/gcroots/nix-shell-*")
    guest.command("cd /")
    return "nix-shell interactive native/APE builds, commands, hook failures, GC roots and namespace restoration passed"


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
