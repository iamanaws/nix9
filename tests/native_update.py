"""Fetch pinned package recipes, build an update, and roll back offline."""

import functools
import http.server
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading

from guest import boot


def tree_hash(path):
    return subprocess.check_output([
        "nix", "--extra-experimental-features", "nix-command", "hash", "path", str(path),
    ], text=True).strip()


def rooted(guest, root):
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing update root: {result}")
    return paths[0]


qemu, image, bootstrap, source, output = sys.argv[1:]
roots = "/usr/local/nix/state/gcroots"
profile = roots + "/update-profile"
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    shutil.copyfile(bootstrap, root / "bootstrap.tar")
    shutil.copyfile(Path(source) / "packages.tar.gz", root / "one.tar.gz")
    with tarfile.open(root / "one.tar.gz") as archive:
        archive.extractall(root, filter="data")
    tree = root / "packages"
    hashes = {"one": (Path(source) / "sha256").read_text().strip()}
    if tree_hash(tree) != hashes["one"]:
        raise RuntimeError("published package archive does not match its hash")
    recipe = tree / "pkgs/sha1sum.nix"
    original = recipe.read_text()
    recipe.chmod(0o644)
    for name, command in (("two", "echo updated > $out/revision"),
                          ("broken", "echo 'update failed' >[1=2]; exit failed")):
        recipe.write_text(original.replace("6l -o $out/bin/sha1sum sha1sum.6",
                                           "6l -o $out/bin/sha1sum sha1sum.6\n    " + command))
        hashes[name] = tree_hash(tree)
        with tarfile.open(root / f"{name}.tar.gz", "w:gz", format=tarfile.USTAR_FORMAT) as archive:
            archive.add(tree, arcname="packages")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://10.0.2.2:{server.server_port}"
            for name in ("one", "two", "broken", "wrong-hash"):
                archive = "two" if name == "wrong-hash" else name
                digest = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" if name == "wrong-hash" else hashes[name]
                expression = (Path(source) / "update.nix").read_text()
                expression = expression.replace("https://example.org/packages.tar.gz", f"{base}/{archive}.tar.gz")
                expression = "{ inspect ? false }:\n" + expression.replace("pkgs.buildEnv {", '''
                  if inspect then builtins.listToAttrs (map (name: {
                    inherit name;
                    value = pkgs.${name}.drvPath;
                  }) [ "cc" "ar" "rc" "patch" "libc" "libmp" "libsec" "libbio" "libregexp"
                       "mk" "yacc" "lex" "libl" "liblua" "lua" "fortune" "sha1sum" ])
                  else pkgs.buildEnv {''')
                (root / f"{name}.nix").write_text(expression.replace(hashes["one"], digest))
            with boot(qemu, image) as guest:
                guest.child.timeout = 600
                guest.command(f"hget -o /tmp/bootstrap.tar {base}/bootstrap.tar")
                guest.command("cd / && tar xf /tmp/bootstrap.tar; rm /tmp/bootstrap.tar")
                guest.command(". /usr/local/pkg/nix9/activate")
                guest.command("webfs -m /mnt/web -T 60000")
                for name in ("one", "two", "broken", "wrong-hash"):
                    guest.command(f"hget -o /tmp/{name}.nix {base}/{name}.nix")
                outputs = {}
                derivations = {}
                for name in ("one", "two"):
                    result = guest.command(f"nix-instantiate /tmp/{name}.nix --eval --strict --json --arg inspect true")
                    derivations[name] = json.loads(re.findall(r"(?m)^\{.*\}$", result)[0])
                    if name == "two":
                        changed = {package: (drv, derivations[name][package])
                                   for package, drv in derivations["one"].items()
                                   if drv != derivations[name][package]}
                        if set(changed) != {"sha1sum"}:
                            raise RuntimeError(f"recipe edit changed unrelated derivations: {changed}")
                    result = guest.command(f"nix-build /tmp/{name}.nix --out-link {roots}/candidate")
                    if name == "two" and "building '" not in result:
                        raise RuntimeError(f"updated recipe was not built natively: {result}")
                    environment = outputs[name] = rooted(guest, roots + "/candidate")
                    guest.command(f"nix-profile {profile} set {environment}")
                    guest.command(f". $nix9/packages/profile {profile}")
                    guest.command("echo -n abc | sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
                    if name == "two":
                        result = guest.command("whatis sha1sum")
                        commands = re.findall(r"/usr/local/nix/store/[a-z0-9]{32}-sha1sum/bin/sha1sum", result)
                        if len(commands) != 1:
                            raise RuntimeError(f"updated command is not active: {result}")
                        guest.command(f"cat {commands[0].removesuffix('/bin/sha1sum')}/revision", "updated")
                if outputs["one"] == outputs["two"]:
                    raise RuntimeError("package update reused the original environment")
                for name, reason in (("wrong-hash", "hash mismatch"), ("broken", "update failed")):
                    guest.command(f"update='nix-build /tmp/{name}.nix --out-link {roots}/candidate'")
                    result = guest.command(f"eval $update && nix-profile {profile} set `{{cat {roots}/candidate}}; echo UPDATE-STATUS:$status")
                    if reason not in result or not re.search(r"(?m)^UPDATE-STATUS:.+$", result):
                        raise RuntimeError(f"invalid update was accepted: {result}")
                    guest.command(f"cat {profile}", outputs["two"])
                    guest.command("echo -n abc | sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
                # Re-evaluate and rebuild with neither a server nor substitutions.
                server.shutdown()
                thread.join()
                guest.command("NIX_CONFIG='substituters ='")
                guest.command(f"nix-build /tmp/two.nix --out-link {roots}/candidate", outputs["two"])
                guest.command("nix-build /tmp/two.nix --check --no-out-link")
                guest.command(f"rm {roots}/candidate; nix-store --gc")
                guest.command(f"nix-profile {profile} rollback")
                guest.command(f". $nix9/packages/profile {profile}")
                guest.command(f"cat {profile}", outputs["one"])
                guest.command("echo -n abc | sha1sum", "a9993e364706816aba3e25717850c26c9cd0d89d")
                guest.command(f"nix-profile {profile} delete 2; nix-store --gc")
                guest.command(f"test ! -e {outputs['two']} && nix-store --verify-path {outputs['one']}")
        finally:
            server.shutdown()
            thread.join()

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "pinned-package-update": "passed",
    "unchanged-packages-reused": "passed",
    "failed-updates-preserve-profile": "passed",
    "offline-rebuild": "passed",
    "rollback-and-gc": "passed",
}, indent=2) + "\n")
