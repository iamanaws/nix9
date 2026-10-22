"""Bootstrap the C toolchain, rebuild it, and run consumers without seed compilers."""

import re


def check_cc(guest, packages, port):
    for name in ("cc.nix", "libc.c"):
        guest.command(f"hget -o /tmp/{name} http://10.0.2.2:{port}/{name}")
    guest.command(f"ccPackages={packages}")
    guest.command("fn ccBuild { nix-build /tmp/cc.nix --argstr packages $ccPackages $* }")
    outputs = {}
    roots = []
    for attribute in ("compiler", "rebuilt", "program", "rebuiltProgram"):
        root = f"/usr/local/nix/state/gcroots/cc-{attribute}"
        roots.append(root)
        guest.command(f"ccBuild -A {attribute} --out-link {root}")
        result = guest.command(f"cat {root}")
        paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-[a-zA-Z0-9+-]+$", result)
        if len(paths) != 1:
            raise RuntimeError(f"missing {attribute} output: {result}")
        outputs[attribute] = paths[0]
        closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"nix-store -qR {paths[0]}")))
        if closure != {paths[0]}:
            raise RuntimeError(f"{attribute} retains build dependencies: {closure}")
    if outputs["compiler"] == outputs["rebuilt"]:
        raise RuntimeError("toolchain was not rebuilt with the native stdenv")
    result = guest.command(f"ccBuild -A rebuilt --out-link {roots[1]}")
    if "building '" in result:
        raise RuntimeError("unchanged toolchain was rebuilt")
    guest.command("nix-shell /tmp/cc.nix --argstr packages $ccPackages -A shell --run 'whatis 6c'", outputs["compiler"] + "/bin/6c")
    guest.command("nix-store --gc")
    for attribute, output in outputs.items():
        guest.command(f"nix-store --verify-path {output}")
        if attribute in ("program", "rebuiltProgram"):
            for name, message in (("answer", "native cc PASS"), ("libc-test", "native libc PASS"), ("ape", "APE cc PASS")):
                guest.command(f"{output}/bin/{name}", message)
    for root in roots:
        guest.command(f"rm {root}")
    guest.command("nix-store --gc")
    for attribute in ("rebuilt", "program", "rebuiltProgram"):
        guest.command(f"test ! -e {outputs[attribute]}")
    return "native 6a/6c/6l/cpp/pcc, compiler rebuild, default stdenv, masked seed compilers, native/APE consumers, preprocessing, invalid C, shell, reuse and GC passed"
