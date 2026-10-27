"""Enter ordinary derivations and mkShell environments without building them."""

import json
from pathlib import Path
import re
import sys

from guest import files_guest
from native_inputs import check_pure_shell, check_shell


qemu, image, bootstrap, output = sys.argv[1:]
fixtures = {"bootstrap.tar": bootstrap, "inputs.nix": Path(__file__).with_name("inputs.nix"),
            "pure-shell.rc": Path(__file__).with_name("pure-shell.rc")}
with files_guest(qemu, image, fixtures) as guest:
    guest.command("cd / && tar xf /tmp/bootstrap.tar; rm /tmp/bootstrap.tar")
    guest.command(". /usr/local/pkg/nix9/activate")
    shell = check_shell(guest, "$nix9/packages")
    check_pure_shell(guest)
    guest.command("PATH=/bin; packageOriginalPATH=$PATH")
    guest.command("mkdir /tmp/package-shell; cp /tmp/inputs.nix /tmp/package-shell/default.nix; cd /tmp/package-shell")
    guest.command("fn packageShell { nix-shell --argstr packages $nix9/packages -A package $* }")
    result = guest.command("nix-instantiate --argstr packages $nix9/packages --eval --strict --json -A package.outPath")
    paths = re.findall(r'(?m)^"(/usr/local/nix/store/[a-z0-9]{32}-shell-package)"$', result)
    if len(paths) != 1:
        raise RuntimeError(f"missing package output path: {result}")
    package = paths[0]
    dry = guest.command("packageShell --dry-run")
    if "building '" in dry:
        raise RuntimeError(f"dry-run built a dependency: {dry}")
    guest.command(f"test ! -e {package}")
    # Check quotes and newlines after the rc environment has been applied.
    guest.command("message='parent message'")
    for flags in ("", "--pure --keep message"):
        result = guest.command(f"packageShell {flags} --run 'echo $packageShellHook; echo $message; cat $messageFilePath; echo shell-temp:$TMPDIR'", "ready")
        for expected in ("spaces, 'quotes', $variables; and a newline\nsecond line",
                         "contents with 'quotes' and $variables\nsecond line"):
            if expected not in result:
                raise RuntimeError(f"shell changed a derivation variable: {result}")
        temporary = re.findall(r"(?m)^shell-temp:(/tmp/[^\s]+)$", result)
        if len(temporary) != 1:
            raise RuntimeError(f"missing shell temporary directory: {result}")
        guest.command(f"test ! -e {temporary[0]} && ~ $message 'parent message'")
    guest.command("packageShell --run 'nix-store --gc && nix-store --check-validity $src $nativeBuildInputs $buildInputs && generate > generated.h && 6c -I . -o main.6 $src && 6l -s -o answer main.6 && ./answer'", "native inputs PASS")
    guest.command("packageShell --pure --run 'flag e +; ~ $IN_NIX_SHELL pure; ~ $packageShellHook ready; generate > generated.h; 6c -I . -o pure-main.6 $src; 6l -s -o pure-answer pure-main.6; ./pure-answer'", "native inputs PASS")
    guest.command(f"test ! -e {package} && test -f answer && test -f generated.h")
    # shell.nix remains useful for custom inputs and hooks; default.nix needs no wrapper.
    guest.command("mkdir /tmp/hello; cp $nix9/hello/* /tmp/hello; cd /tmp/hello; rm shell.nix")
    guest.command("nix-shell --pure --run 'mk && ./6.out && mk clean'", "hello from nix9")
    guest.command("test ! -e hello.6 && test ! -e 6.out")
    guest.command("~ $PATH $packageOriginalPATH")
    guest.command("for(i in 1 2 3 4 5) { if(test -e /usr/local/nix/state/gcroots/nix-shell-*) sleep 1 }; test ! -e /usr/local/nix/state/gcroots/nix-shell-*")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "ordinary-derivation": "passed",
    "dependencies-only": "passed",
    "derivation-environment": "passed",
    "pure-environment": "passed",
    "gc-during-shell": "passed",
    "default-nix-fallback": "passed",
    "mkShell": shell,
}, indent=2) + "\n")
