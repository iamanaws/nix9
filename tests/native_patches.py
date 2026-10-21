"""Apply native source patches, exercise phase hooks, and reject failed hunks."""

import json
from pathlib import Path
import re
import sys

from guest import files_guest


qemu, image, archive, output = sys.argv[1:]
fixtures = {"bootstrap.tar": archive, "patches.nix": Path(__file__).with_name("patches.nix")}
root = "/usr/local/nix/state/gcroots/patch-tests"
with files_guest(qemu, image, fixtures) as guest:
    guest.command("cd / && tar xf /tmp/bootstrap.tar")
    guest.command(". /usr/local/pkg/nix9/activate")
    guest.command("nix-build $nix9/shell.nix --out-link /usr/local/nix/state/gcroots/toolchain")
    guest.command("NIX_CONFIG='substituters ='")
    guest.command("fn patchBuild { nix-build /tmp/patches.nix --argstr packages $nix9/packages -A $1 --out-link " + root + " }")
    for name, message in (("default", "patched"), ("empty", "original"), ("flags", "patched"),
                          ("override", "custom"), ("skipped", "original")):
        guest.command(f"patchBuild {name}")
        guest.command(f"p=`{{cat {root}}}; cat $p/message", message)
        result = guest.command("cat $p/order")
        expected = "build\ninstall" if name == "skipped" else "prePatch\npostPatch\nbuild\ninstall"
        if expected + "\n" not in result:
            raise RuntimeError(f"incorrect patch phase order: {result}")
    for name, reason in (("rejected", "unable to find hunk offset"),
                         ("preFailure", "pre-patch-failed"), ("postFailure", "post-patch-failed")):
        result = guest.command(f"patchBuild {name}; echo PATCH-STATUS:$status")
        if reason not in result or not re.search(r"(?m)^PATCH-STATUS:.*cc9exit=100$", result):
            raise RuntimeError(f"patch failure was not propagated: {result}")
    guest.command(f"nix-build $nix9/packages -A patch --check --no-out-link")

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "patches": "ordered patches, flags, hooks, overrides, skipped phases and failures passed",
}, indent=2) + "\n")
