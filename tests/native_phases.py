"""Check native build phases, overrides and failure propagation."""

import re


def check_phases(guest, packages, port):
    guest.command("mkdir /tmp/phase-source /tmp/phase-source/nested")
    guest.command("echo unpack > /tmp/phase-source/trace")
    guest.command("echo original > /tmp/phase-source/nested/.message")
    guest.command(f"hget -o /tmp/phases.nix http://10.0.2.2:{port}/phases.nix")
    guest.command(f"phasePackages={packages}")
    guest.command("fn phases { nix-build /tmp/phases.nix --argstr packages $phasePackages $* }")
    for options, expected in (
        ("", "unpack\nbuild\ncheck\ninstall"),
        ("--arg doCheck false", "unpack\nbuild\ninstall"),
        ("--arg customUnpack true", "custom-unpack\nbuild\ncheck\ninstall"),
    ):
        guest.command(f"phases {options} --out-link /usr/local/nix/state/gcroots/phases")
        result = guest.command("cat `{cat /usr/local/nix/state/gcroots/phases}")
        if expected + "\n" not in result:
            raise RuntimeError(f"incorrect phase order: {result}")
    for phase in ("unpack", "build", "check", "install"):
        result = guest.command(f"phases --argstr fail {phase} --no-out-link; echo PHASE-STATUS:$status")
        if not re.search(r"(?m)^PHASE-STATUS:.*cc9exit=100$", result) or f"phase-failure-{phase}" not in result:
            raise RuntimeError(f"{phase} failure was not reported: {result}")
    guest.command("rm /usr/local/nix/state/gcroots/phases")
    return "phase order, optional checks, unpack override and failures passed"
