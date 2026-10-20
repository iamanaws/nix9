"""Check native build phases, overrides and failure propagation."""

import re


def check_mk_phases(guest, packages, port):
    guest.command(f"hget -o /tmp/mk-phases.nix http://10.0.2.2:{port}/mk-phases.nix")
    guest.command(f"mkPhasePackages={packages}")
    guest.command("fn mkPhases { nix-build /tmp/mk-phases.nix --argstr packages $mkPhasePackages -A $1 --out-link $2 }")
    root = "/usr/local/nix/state/gcroots/mk-phases"
    for name, file, expected in (
        ("default", "/bin/message", "built"),
        ("custom", "/bin/message", "built"),
        ("override", "", "overridden"),
        ("noMkfile", "", "hook"),
        ("singleCommand", "", "single"),
    ):
        guest.command(f"mkPhases {name} {root}")
        guest.command(f"mkResult=`{{cat {root}}}")
        guest.command(f"cat $mkResult{file}", expected)
    for name in ("failBuild", "failInstall"):
        result = guest.command(f"mkPhases {name} {root}; echo MK-PHASE-STATUS:$status")
        if not re.search(r"(?m)^MK-PHASE-STATUS:.*cc9exit=100$", result):
            raise RuntimeError(f"{name} failure was not propagated: {result}")
    guest.command(f"rm {root}")
    return "default mk phases, flags, custom mkfile, overrides, absent mkfile, buildCommand and failures passed"


def check_overrides(guest, packages, port):
    guest.command(f"hget -o /tmp/overrides.nix http://10.0.2.2:{port}/overrides.nix")
    guest.command(f"overridePackages={packages}")
    guest.command("fn overrides { nix-build /tmp/overrides.nix --argstr packages $overridePackages -A $1 --out-link $2 }")
    for attribute in ("unchanged", "injection", "metadata"):
        guest.command(f"nix-instantiate --eval /tmp/overrides.nix --argstr packages $overridePackages -A {attribute}", "true")
    outputs = {}
    for name, version, message, hooks in (
        ("original", "1", "original", "original"),
        ("annotated", "1", "original", "original"),
        ("changed", "2", "changed", "original\nchanged"),
        ("chained", "3", "changed", "original\nchanged\nchained"),
        ("direct", "4", "direct", "original"),
        ("called", "5", "called", "original"),
        ("arguments", "6", "called", "original"),
        ("argumentChain", "7", "called chained", "original"),
        ("mixed", "8", "mixed", "original\nattrs"),
    ):
        root = f"/usr/local/nix/state/gcroots/override-{name}"
        guest.command(f"overrides {name} {root}")
        result = guest.command(f"cat {root}")
        paths = re.findall(rf"(?m)^/usr/local/nix/store/[a-z0-9]{{32}}-override-example-{version}$", result)
        if len(paths) != 1:
            raise RuntimeError(f"missing overridden package: {result}")
        package = outputs[name] = paths[0]
        guest.command(f"cat {package}/message", message)
        result = guest.command(f"cat {package}/hooks")
        if hooks + "\n" not in result:
            raise RuntimeError(f"incorrect overridden hooks: {result}")
    if outputs["annotated"] != outputs["original"]:
        raise RuntimeError("metadata changed the build output")
    guest.command("nix-store --gc")
    for name, package in outputs.items():
        guest.command(f"nix-store --verify-path {package}")
        if name in ("changed", "chained"):
            guest.command(f"dependency=`{{cat {package}/dependency}}; cat $dependency/include/override.h", "dependency")
        else:
            guest.command(f"test ! -e {package}/dependency")
        if name in ("arguments", "argumentChain", "mixed"):
            guest.command(f"cat {package}/argument", "replacement")
        elif name == "called":
            guest.command(f"cat {package}/argument", "dependency")
        else:
            guest.command(f"test ! -e {package}/argument")
        guest.command(f"rm /usr/local/nix/state/gcroots/override-{name}")
    guest.command(f"cat {outputs['original']}/message", "original")
    return "callPackage injection, defaults, argument overrides, dependency replacement, metadata, passthru, overrideAttrs and mixed chaining passed"


def check_phases(guest, packages, port):
    guest.command("mkdir /tmp/phase-source /tmp/phase-source/nested")
    guest.command("echo unpack > /tmp/phase-source/trace")
    guest.command("echo original > /tmp/phase-source/nested/.message")
    guest.command(f"hget -o /tmp/phases.nix http://10.0.2.2:{port}/phases.nix")
    guest.command(f"phasePackages={packages}")
    guest.command("fn phases { nix-build /tmp/phases.nix --argstr packages $phasePackages $* }")
    custom = "--arg phases '[\"unpackPhase\" \"generatePhase\" \"buildPhase\" \"checkPhase\" \"installPhase\"]'"
    for options, expected in (
        ("", "unpack\nbuild\ncheck\ninstall"),
        ("--arg doCheck false", "unpack\nbuild\ninstall"),
        ("--arg customUnpack true", "custom-unpack\nbuild\ncheck\ninstall"),
        ("--arg hooks true", "preUnpack\nunpack\npostUnpack\npreBuild\nbuild\npostBuild\npreCheck\ncheck\npostCheck\npreInstall\ninstall\npostInstall"),
        ("--arg hooks true --arg doCheck false", "preUnpack\nunpack\npostUnpack\npreBuild\nbuild\npostBuild\npreInstall\ninstall\npostInstall"),
        ("--arg hooks true --arg singleCommand true --argstr fail preUnpack", "single-command"),
        (custom, "unpack\ngenerate\nbuild\ncheck\ninstall"),
        (custom + " --arg doCheck false", "unpack\ngenerate\nbuild\ninstall"),
        (custom + " --arg hooks true", "preUnpack\nunpack\npostUnpack\npreGenerate\ngenerate\npostGenerate\npreBuild\nbuild\npostBuild\npreCheck\ncheck\npostCheck\npreInstall\ninstall\npostInstall"),
        ("--arg phases '[\"unpackPhase\" \"generatePhase\" \"installPhase\"]' --argstr fail build", "unpack\ngenerate\ninstall"),
        ("--arg phases '[\"unpackPhase\" \"generatePhase\" \"checkPhase\" \"buildPhase\" \"installPhase\"]'", "unpack\ngenerate\ncheck\nbuild\ninstall"),
        ("--arg phases '[\"missingPhase\"]' --arg singleCommand true", "single-command"),
    ):
        guest.command(f"phases {options} --out-link /usr/local/nix/state/gcroots/phases")
        result = guest.command("cat `{cat /usr/local/nix/state/gcroots/phases}")
        if expected + "\n" not in result:
            raise RuntimeError(f"incorrect phase order: {result}")
    for phase in ("unpack", "build", "check", "install"):
        result = guest.command(f"phases --argstr fail {phase} --no-out-link; echo PHASE-STATUS:$status")
        if not re.search(r"(?m)^PHASE-STATUS:.*cc9exit=100$", result) or f"phase-failure-{phase}" not in result:
            raise RuntimeError(f"{phase} failure was not reported: {result}")
    for hook in ("preUnpack", "postUnpack", "preBuild", "postBuild", "preCheck", "postCheck", "preInstall", "postInstall"):
        result = guest.command(f"phases --arg hooks true --argstr fail {hook} --no-out-link; echo PHASE-STATUS:$status")
        if not re.search(r"(?m)^PHASE-STATUS:.*cc9exit=100$", result) or f"phase-failure-{hook}" not in result:
            raise RuntimeError(f"{hook} failure was not reported: {result}")
    for phase in ("generate", "preGenerate", "postGenerate"):
        result = guest.command(f"phases {custom} --arg hooks true --argstr fail {phase} --no-out-link; echo PHASE-STATUS:$status")
        if not re.search(r"(?m)^PHASE-STATUS:.*cc9exit=100$", result) or f"phase-failure-{phase}" not in result:
            raise RuntimeError(f"{phase} failure was not reported: {result}")
    result = guest.command("phases --arg phases '[\"missingPhase\"]' --no-out-link; echo PHASE-STATUS:$status")
    if "unknown build phase 'missingPhase'" not in result or not re.search(r"(?m)^PHASE-STATUS:.+$", result):
        raise RuntimeError(f"unknown phase was not rejected: {result}")
    guest.command("rm /usr/local/nix/state/gcroots/phases")
    return "default/custom phase order, hooks, shared state, skipped phases, optional checks, unpack override, buildCommand and failures passed"
