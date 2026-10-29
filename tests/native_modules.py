"""Evaluate pinned Nix modules offline and build a composed machine configuration."""

import json
from pathlib import Path
import re
import sys
import time

from guest import files_guest


qemu, image, archive, output = sys.argv[1:]
fixtures = {"bootstrap.tar": archive}
for name in ("modules.nix", "module-import.nix", "module-system.nix", "module-probe.rc"):
    fixtures[name] = Path(__file__).with_name(name)
with files_guest(qemu, image, fixtures, compress=True) as guest:
    guest.child.timeout = 900
    guest.command("cd / && tar xf /tmp/bootstrap.tar")
    guest.command(". /usr/local/pkg/nix9/activate")
    guest.command("nix9-rebuild init test")
    guest.command("NIX_CONFIG='substituters ='")
    start = time.monotonic()
    result = guest.command("rc /tmp/module-probe.rc")
    seconds = time.monotonic() - start
    values = [json.loads(line) for line in result.splitlines() if line.startswith('{"conditional"')]
    expected = {"conditional": "enabled", "enabled": True,
                "message": "forced", "order": ["first", "last"]}
    if values != [expected]:
        raise RuntimeError(f"incorrect module configuration: {result}")
    samples = [line.split() for line in result.splitlines() if line.startswith("nix-instantiate ")]
    if not samples:
        raise RuntimeError("missing native evaluator memory samples")
    peak_kib = max(int(sample[9]) for sample in samples)
    for scenario, reason in (("invalid-type", "boolean"), ("unknown-option", "does not exist")):
        result = guest.command(f"nix-instantiate --eval --strict /tmp/modules.nix --argstr scenario {scenario}; echo MODULE-ERROR:$status")
        if not re.search(r"(?m)^MODULE-ERROR:.+", result) or reason not in result:
            raise RuntimeError(f"module error was not reported: {scenario}: {result}")
    guest.command("nix9-rebuild switch /tmp/module-system.nix")
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("cat /cfg/nix9/files/message", "imported and overridden")
    guest.command("cat /cfg/nix9/files/second", "merged")
    guest.command("echo `{cat /dev/sysname}", "module-host")
    guest.command("whatis fortune")
    guest.command("echo 'let p=import <nix9>; in p.mkSystem {hostName=\"invalid\"; assertions=[{assertion=false; message=\"fixture assertion\";}];}' > /tmp/module-invalid.nix")
    result = guest.command("nix9-rebuild switch /tmp/module-invalid.nix; echo MODULE-ERROR:$status")
    if "fixture assertion" not in result or not re.search(r"(?m)^MODULE-ERROR:.+", result):
        raise RuntimeError("failed module assertion was accepted")
    guest.command("echo `{cat /dev/sysname}", "module-host")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "status": "passed", "offline-module-evaluation": "passed",
    "composed-system": "passed", "error-reporting": "passed",
    "evaluation-wall-seconds": seconds, "peak-sampled-kib": peak_kib,
}, indent=2) + "\n")
