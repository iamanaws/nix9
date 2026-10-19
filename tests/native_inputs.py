"""Check build tools and native/APE library discovery without namespace leaks."""

import re


def check_inputs(guest, packages, port):
    guest.command(f"hget -o /tmp/inputs.nix http://10.0.2.2:{port}/inputs.nix")
    guest.command(f"inputPackages={packages}")
    guest.command("fn inputs { nix-build /tmp/inputs.nix --argstr packages $inputPackages -A $1 --out-link $2 }")
    outputs = {}
    for kind in ("native", "ape"):
        root = f"/usr/local/nix/state/gcroots/{kind}-inputs"
        guest.command(f"inputs {kind} {root}")
        result = guest.command(f"cat {root}")
        paths = re.findall(rf"(?m)^/usr/local/nix/store/[a-z0-9]{{32}}-{kind}-inputs$", result)
        if len(paths) != 1:
            raise RuntimeError(f"missing {kind} input test output: {result}")
        outputs[kind] = paths[0]
    result = guest.command(f"nix-store -qR {outputs['native']}")
    closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result))
    if closure != {outputs["native"]}:
        raise RuntimeError(f"static native program retains build dependencies: {closure}")
    guest.command("test ! -e /sys/include/answer.h && test ! -e /sys/include/ape/answer.h")
    guest.command("test ! -e /amd64/lib/libanswer.a && test ! -e /amd64/lib/ape/libanswer.a")
    guest.command("nix-store --gc")
    for kind, package in outputs.items():
        guest.command(f"{package}/bin/answer", f"{kind} inputs PASS")
        guest.command(f"nix-store --verify-path {package}")
        guest.command(f"rm /usr/local/nix/state/gcroots/{kind}-inputs")
    return "build tools, POSIX PATH, separate native/APE headers and libraries, namespace isolation and GC passed"
