"""Compare native evaluation with host Nix, including imports and failures."""

import json
import re
import subprocess


def eval_fixtures(root):
    expressions = {
        "eval-module.nix": "x: { answer = x * 2; }",
        "eval-data": "local file\n",
        "eval-cases.nix": r'''
          let
            factorial = n: if n == 0 then 1 else n * factorial (n - 1);
            drv = derivation {
              name = "eval-example"; system = "x86_64-plan9";
              builder = "/bin/rc"; args = [ "-c" "echo hello > $out" ];
            };
          in {
            arithmetic = [ (6 * 7) (13 / 2) 1.5 (-3) ];
            recursion = factorial 6;
            lazy = (x: 42) (throw "unused");
            branch = if true then "yes" else throw "unused";
            attrs = ({ a = 1; b = 2; } // { b = 3; }).b;
            lists = builtins.map (x: x * 2) (builtins.genList (x: x) 8);
            fold = builtins.foldl' (a: b: a + b) 0 [ 1 2 3 4 ];
            strings = "hello ${toString 42}";
            regex = builtins.match "([a-z]+)-([0-9]+)" "nix-9";
            json = builtins.fromJSON (builtins.toJSON { a = [ true null 42 ]; });
            toml = builtins.fromTOML "[package]\nname = \"nix9\"\nversion = 1";
            hash = builtins.hashString "sha256" "nix9";
            version = builtins.compareVersions "2.10" "2.9";
            caught = (builtins.tryEval (throw "expected")).success;
            imported = import ./eval-module.nix 21;
            file = builtins.readFile ./eval-data;
            derivation = { inherit (drv) drvPath outPath type; };
          }
        ''',
    }
    files = {}
    for name, text in expressions.items():
        path = root / name
        path.write_text(text)
        files[name] = path
    expected = subprocess.check_output([
        "nix-instantiate", "--store", "dummy://", "--eval", "--strict", "--json",
        str(files["eval-cases.nix"]),
    ], text=True)
    path = root / "eval-expected.json"
    path.write_text(json.dumps(json.loads(expected), sort_keys=True, separators=(",", ":")) + "\n")
    files[path.name] = path
    return files


def check_nix_eval(guest):
    guest.command("elf2aout /tmp/nix-eval.elf /tmp/nix-eval && chmod +x /tmp/nix-eval")
    cli = "/tmp/nix-eval --store /tmp/nix9-eval-store"
    guest.command("/tmp/nix-eval --help", "Evaluate a Nix expression and print strict JSON.")
    guest.command(f"{cli} --expr '1 + 2'", "3")
    guest.command(f"{cli} /tmp/eval-cases.nix > /tmp/eval-result.json")
    guest.command("cmp /tmp/eval-result.json /tmp/eval-expected.json")
    for args, message in (
        ("", "Usage:"),
        ("--add-root /tmp/eval-root --expr '42'", "--add-root requires --instantiate"),
        ("--instantiate --add-root", "--add-root requires a path"),
        ("--instantiate --add-root '' --expr '42'", "--add-root requires a path"),
        ("--instantiate --add-root /tmp/eval-root --expr '42'", "expected a derivation"),
        ("--expr 'let x = ; in x'", "syntax error"),
        ("--expr '1 + true'", "Boolean"),
        ("--expr 'throw \"expected failure\"'", "expected failure"),
        ("--expr 'assert false; 1'", "assertion"),
        ("--expr '{ ok = 1; bad = throw \"strict JSON\"; }'", "strict JSON"),
        ("--expr 'builtins.findFile [{prefix=\"r\";path=\"https://example.invalid/x\";}] \"r\"'", "cannot be downloaded"),
    ):
        output = guest.command(f"{cli} {args}; echo EVAL-STATUS:$status")
        if not re.search(r"(?m)^EVAL-STATUS:.*cc9exit=1$", output) or message not in output:
            raise RuntimeError(f"expected evaluator failure ({message}): {args}\n{output}")
    guest.command(f"{cli} --expr '(import /tmp/eval-module.nix 21).answer'", "42")
    guest.command("NIX_REMOTE=/tmp/nix9-eval-store /tmp/nix-eval --expr '7 * 6'", "42")
    return ["host JSON comparison", "language", "builtins", "local imports", "derivation paths",
            "strict errors", "unsupported fetching", "store environment"]
