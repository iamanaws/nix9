"""Exercise the public CLI, source references and exact-bundle deployment offline."""

import json
from pathlib import Path
import re
import sys

from guest import files_guest


def rejected(guest, command, reason):
    result = guest.command(command + "; echo CLI-ERROR:$status")
    if not re.search(r"(?m)^CLI-ERROR:.+", result) or reason not in result or "syntax error" in result:
        raise RuntimeError(f"unexpected rejection: {command}: {result}")


qemu, image, archive, output = sys.argv[1:]
files = {"bootstrap.tar": archive, "cli.nix": Path(__file__).with_name("cli.nix")}
with files_guest(qemu, image, files) as guest:
    guest.child.timeout = 900
    guest.command("cd / && tar xf /tmp/bootstrap.tar")
    guest.command(". /usr/local/pkg/nix9/activate")
    guest.command("cli=$nix9/bin/nix9; @{ rfork e; nix9=(); $cli help }")
    guest.command("{ echo exit; cat $nix9/bin/nix9 $nix9/bin/nix9-rebuild $nix9/packages/system/manage.rc $nix9/packages/installation/*.rc; } > /tmp/cli-syntax.rc")
    guest.command("rc -b /tmp/cli-syntax.rc")
    guest.command("test ! -e $nix9/bin/nix9-deploy && test ! -e $nix9/bin/nix9-session")
    for action in ("init", "check", "select", "deploy"):
        rejected(guest, "nix9-rebuild " + action, "unknown action")
    for action in ("build", "switch", "rollback"):
        rejected(guest, "nix9 " + action, "unknown action")
    guest.command("nix9 status", "machine -")
    rejected(guest, "nix9 status --health", "no recorded booted system")
    rejected(guest, "nix9 show --health", "only valid with status")
    rejected(guest, "nix9 status --health --health", "duplicate --health")
    guest.command("nix9 init local; nix9 init local")
    rejected(guest, "nix9 init other", "identity is already fixed")
    guest.command("mkdir -p /usr/glenda/site; cp /tmp/cli.nix /usr/glenda/site/default.nix")
    guest.command("cd /usr/glenda/site")
    rejected(guest, "nix9 show", "no retained build")
    rejected(guest, "nix9 deploy", "machine names or --all")
    rejected(guest, "nix9 select-root", "machine names or --all")
    rejected(guest, "nix9 deploy --prepare --select local", "mutually exclusive")
    rejected(guest, "nix9 deploy --all local", "machine names or --all")
    rejected(guest, "nix9 deploy --file default.nix --from /tmp/bundle local", "mutually exclusive")
    guest.command("nix9 deploy --prepare local")
    roots = re.findall(r"(?m)^/usr/local/nix/state/gcroots/installations/[0-9a-f]{40}$",
                       guest.command("ls /usr/local/nix/state/gcroots/installations/*"))
    if len(roots) != 1:
        raise RuntimeError(f"expected one source reference: {roots}")
    reference = roots[0]
    bundle = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat " + reference))[0]
    guest.command("test ! -e /usr/local/nix/state/gcroots/machines/local/system")
    guest.command("echo 'assert false; {}' > default.nix")
    guest.command("nix9 show --file ././default.nix local", "Installation cli")
    guest.command("nix9 status local", "local prepared " + re.findall(
        r"(?m)^/usr/local/nix/store/\S+$", guest.command("cat " + bundle + "/systems/local"))[0])
    guest.command("nix9 deploy --select local")
    rejected(guest, "nix9 deploy --prepare local", "previous bundle retained")
    guest.command("cat " + reference, bundle)
    history = guest.command("nix9-rebuild list")
    guest.command("cd /tmp")
    guest.command("nix9 show --from " + reference, "Installation cli")
    guest.command("nix9 deploy --select --from " + reference + " --all")
    guest.command("nix9 deploy --from " + reference + " local")
    if guest.command("nix9-rebuild list") != history:
        raise RuntimeError("exact-bundle deployment duplicated a generation")
    guest.command("cp /tmp/cli.nix /usr/glenda/site/default.nix; cd /usr/glenda/site")
    guest.command("nix9 deploy --all")
    guest.command("nix9 status", "reboot required")
    guest.command(". /usr/local/pkg/nix9/system")
    guest.command("nix9 status", "refresh no")
    guest.command("nix9-rebuild status", "refresh no")
    guest.command("for(file in /usr/local/nix/state/gcroots/installations/.candidates/*) test ! -e $file")
    guest.command("nix-store --gc; nix-store --verify-path " + bundle)
    guest.command("nix9 show local", "Installation cli")
    print("PASS: command split, explicit targets, source reuse, failed-build recovery, exact bundles and retained closures", flush=True)

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({"status": "passed", "checks": [
    "command-split", "explicit-targets", "source-reference", "inspection-without-evaluation",
    "prepare-without-selection", "failed-build-retention", "exact-bundle", "generation-reuse",
    "local-status", "candidate-cleanup", "gc-retention",
]}, indent=2) + "\n")
