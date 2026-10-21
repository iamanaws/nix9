"""Exercise upstream nix-build with native builders and file roots."""

from pathlib import Path
import re

from nix_repair import check_repairs


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
    guest.command("cliBuild /tmp/nix-build.nix -A hello --check")
    guest.command("test `{wc -l < /tmp/nix9-cli-count} -eq 2")
    guest.command("cat $output", "hello")
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
    guest.command("multipleOut=`{cat /tmp/nix9-cli-multiple-out}; cliStore --gc")
    guest.command("test ! -e $multipleOut")
    guest.command("cliBuild /tmp/nix-build.nix -A multiple.dev --check -o $roots/multiple")
    guest.command("test ! -e $multipleOut; cat `{cat $roots/multiple-dev}", "headers")
    guest.command("cliBuild /tmp/nix-build.nix -A other --dry-run -o $roots/dry")
    guest.command("test ! -e $roots/dry && test ! -e /tmp/nix9-cli-other")
    for args, reason, status in (("-A other -o /tmp/outside-root", "output roots must be", 1),
                                 ("--run-env -A hello", "has no mkShell launcher", 1),
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
    check_build_checks(guest)
    check_repairs(guest)
    return ["evaluation and build", "reuse", "root replacement", "file roots", "arguments", "multiple outputs",
            "dry run", "no output root", "failure status", "rebuild checks", "offline repair builds", "GC"]


def check_build_checks(guest):
    guest.command("rm /tmp/nix9-cli-other")
    result = guest.command("cliBuild /tmp/nix-build.nix -A other --check; echo CHECK-STATUS:$status")
    if "checking is not possible" not in result or not re.search(r"(?m)^CHECK-STATUS:.*cc9exit=1$", result):
        raise RuntimeError(f"check accepted an unbuilt output: {result}")
    guest.command("test ! -e /tmp/nix9-cli-other")
    guest.command("echo original > /tmp/nix9-check-message")
    guest.command("cliBuild /tmp/nix-build.nix -A checked -o $roots/checked")
    guest.command("cliBuild /tmp/nix-build.nix -A checked.dev -o $roots/checked")
    guest.command("checkOut=`{cat $roots/checked}; checkDev=`{cat $roots/checked-dev}")
    for name in ("Out", "Dev"):
        guest.command(f"cliStore --dump $check{name} > /tmp/check-{name}.nar")
    guest.command("echo /tmp/n9-cli-build/store/* > /tmp/check-store-before")
    guest.command("cliBuild /tmp/nix-build.nix -A checked --check -o $roots/checked")
    guest.command("test `{wc -l < /tmp/nix9-check-count} -eq 2")
    guest.command("cliStore --query --references $checkDev > /tmp/check-refs")
    guest.command("grep '^'^$checkOut^'$' /tmp/check-refs; grep '^'^$checkDev^'$' /tmp/check-refs")
    guest.command("echo changed > /tmp/nix9-check-message")
    for options, reason, status in (
        ("", "may not be deterministic", 104),
        ("--keep-failed", "may not be deterministic", 104),
        ("missing", "did not produce 'dev'", 1),
        ("fail", "check-builder-failed", 100),
    ):
        if options in ("missing", "fail"):
            guest.command(f"echo flag > /tmp/nix9-check-{options}")
            flags = ""
        else:
            flags = options
        result = guest.command(f"cliBuild /tmp/nix-build.nix -A checked.dev --check {flags} --no-out-link; echo CHECK-STATUS:$status")
        if reason not in result or not re.search(rf"(?m)^CHECK-STATUS:.*cc9exit={status}$", result):
            raise RuntimeError(f"incorrect check failure ({options}): {result}")
        if options == "--keep-failed":
            guest.command("grep '^changed$' $checkOut.check; test ! -e $checkDev.check")
            guest.command("rm $checkOut.check")
        if options in ("missing", "fail"):
            guest.command(f"rm /tmp/nix9-check-{options}")
        for name in ("Out", "Dev"):
            guest.command(f"cliStore --dump $check{name} > /tmp/check-current.nar; cmp /tmp/check-current.nar /tmp/check-{name}.nar")
        guest.command("cliStore --verify-path $checkOut $checkDev")
        guest.command("echo /tmp/n9-cli-build/store/* > /tmp/check-store-after; cmp /tmp/check-store-before /tmp/check-store-after")
    guest.command("echo original > /tmp/nix9-check-message")
    guest.command("cliBuild /tmp/nix-build.nix -A checked --check -o $roots/checked")
    guest.command("test `{wc -l < /tmp/nix9-check-count} -eq 7")
    guest.command("rm $roots/checked $roots/checked-dev; cliStore --gc")
    guest.command("test ! -e $checkOut && test ! -e $checkDev")
