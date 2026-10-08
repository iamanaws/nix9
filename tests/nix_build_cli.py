"""Exercise upstream nix-build with native builders and file roots."""

from pathlib import Path
import re


def build_cli_fixtures():
    return {"nix-build.nix": Path(__file__).with_name("nix-build.nix")}


def check_nix_build_cli(guest):
    guest.command("/tmp/nix-build --help", "Usage: nix-build [OPTIONS] [FILES...]")
    guest.command("/tmp/nix-build --store invalid:// --version", "nix-build (Nix) 2.34.8")
    guest.command("clistore='local?store=/tmp/n9-cli-build/store&state=/tmp/n9-cli-build/state&log=/tmp/n9-cli-build/log'")
    guest.command("fn cliBuild { /tmp/nix-build --store $clistore $* }")
    guest.command("fn cliStore { /tmp/nix-store --store $clistore $* }")
    guest.command("roots=/tmp/n9-cli-build/state/gcroots")
    guest.command("cliBuild /tmp/nix-build.nix -A hello")
    guest.command("output=`{cat $roots/result}; cat $output", "hello")
    result = guest.command("cliBuild /tmp/nix-build.nix -A hello")
    if "building '" in result:
        raise RuntimeError("nix-build rebuilt a valid output")
    guest.command("test `{wc -l < /tmp/nix9-cli-count} -eq 1")
    guest.command("cliStore --gc; cliStore --verify-path $output")
    # Change the source and reuse the default root without removing it.
    guest.command("oldOutput=$output; sed 's/\"hello\"/\"changed\"/' /tmp/nix-build.nix > /tmp/changed.nix; cp /tmp/changed.nix /tmp/nix-build.nix")
    guest.command("cliBuild /tmp/nix-build.nix -A hello")
    guest.command("output=`{cat $roots/result}; cat $output", "changed")
    guest.command("cliStore --gc; cliStore --verify-path $output; test ! -e $oldOutput")
    guest.command("cliBuild /tmp/nix-build.nix -A hello --argstr message custom -o $roots/custom")
    guest.command("cat `{cat $roots/custom}", "custom")
    guest.command("cliBuild /tmp/nix-build.nix -A multiple.dev -o $roots/multiple")
    guest.command("cat `{cat $roots/multiple-dev}", "headers")
    guest.command("cliBuild /tmp/nix-build.nix -A other --dry-run -o $roots/dry")
    guest.command("test ! -e $roots/dry && test ! -e /tmp/nix9-cli-other")
    for args, reason, status in (("-A other -o /tmp/outside-root", "output roots must be", 1),
                                 ("--run-env", "nix-shell is not supported", 1),
                                 ("-A failed", "failed", 100)):
        result = guest.command(f"cliBuild /tmp/nix-build.nix {args}; echo BUILD-STATUS:$status")
        if not re.search(rf"(?m)^BUILD-STATUS:.*cc9exit={status}$", result) or reason not in result:
            raise RuntimeError(f"nix-build did not reject {args}: {result}")
    guest.command("test ! -e /tmp/outside-root; test `{cat $roots/result} '=' $output")
    result = guest.command("cliBuild --expr '(import /tmp/nix-build.nix {}).other' --no-out-link")
    paths = re.findall(r"(?m)^/tmp/n9-cli-build/store/[a-z0-9]{32}-cli-other$", result)
    if len(paths) != 1:
        raise RuntimeError(f"nix-build did not print its output: {result}")
    guest.command(f"cat {paths[0]}", "other")
    guest.command(f"cliStore --gc; test ! -e {paths[0]}")
    guest.command("cat $output", "changed")
    guest.command("rm $roots/result $roots/custom $roots/multiple-dev; cliStore --gc")
    guest.command("test ! -e $output")
    return ["evaluation and build", "reuse", "root replacement", "file roots", "arguments", "multiple outputs",
            "dry run", "no output root", "failure status", "GC"]
