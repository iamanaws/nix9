"""Record the fixed inputs in a generated native package set."""

import json
import os
from pathlib import Path
import subprocess
import sys


root = Path(sys.argv[1]).resolve()
expression = '''
let
  root = /. + builtins.getEnv "NIX9_PACKAGE_ROOT";
  definitions = import (root + "/pkgs/packages.nix") {
    sources = builtins.mapAttrs (name: _: root + "/sources/${name}") (builtins.readDir (root + "/sources"));
  };
in builtins.mapAttrs (_: definition:
  builtins.mapAttrs (_: value: if builtins.isPath value then toString value else null) definition.args
) definitions
'''
paths = json.loads(subprocess.check_output(
    ["nix-instantiate", "--store", "dummy://", "--eval", "--strict", "--json", "--expr", expression],
    env={**os.environ, "NIX9_PACKAGE_ROOT": str(root)}))
hashes = {}


def hash_path(path):
    if path not in hashes:
        hashes[path] = subprocess.check_output(
            ["nix", "--extra-experimental-features", "nix-command", "hash", "path", path], text=True).strip()
    return hashes[path]


manifest = {
    "tools": hash_path(str(root / "tools")),
    "packages": {name: {argument: hash_path(path) for argument, path in arguments.items() if path is not None}
                 for name, arguments in paths.items()},
}
(root / "input-hashes.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
