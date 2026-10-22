"""Build a standalone project and check its explicit GC root."""

import re


def check_project(guest, port):
    guest.command("nix-instantiate --eval --expr 'let p=import /usr/local/pkg/native-packages; a={name=\"alias-check\"; buildCommand=\"echo alias > $out\";}; in (p.mkDerivation a).drvPath == (p.stdenv.mkDerivation a).drvPath'", "true")
    includes = ("/amd64/mkfile", "/sys/src/mkfile.proto", "/sys/src/cmd/mkone", "/sys/src/cmd/mklib", "/sys/src/cmd/mkmany", "/sys/src/cmd/mksyslib")
    guest.command("echo host-mkfile-unavailable > /tmp/host-mkfile")
    for file in includes:
        guest.command(f"bind /tmp/host-mkfile {file}")
    mk_root = "/usr/local/nix/state/gcroots/native-mk"
    guest.command(f"nix-build /usr/local/pkg/native-packages -A mk --out-link {mk_root}")
    result = guest.command(f"cat {mk_root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-mk$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing native mk output: {result}")
    native_mk = paths[0]
    closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"nix-store -qR {native_mk}")))
    if closure != {native_mk}:
        raise RuntimeError(f"native mk retains build dependencies: {closure}")
    guest.command("mkdir /tmp/hello")
    for name in ("default.nix", "package.nix", "shell.nix", "hello.c", "mkfile"):
        guest.command(f"hget -o /tmp/hello/{name} http://10.0.2.2:{port}/project/{name}")
    guest.command("cd /tmp/hello")
    guest.command("nix-build --out-link /usr/local/nix/state/gcroots/hello")
    result = guest.command("cat /usr/local/nix/state/gcroots/hello")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-hello$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing standalone output: {result}")
    package = paths[0]
    result = guest.command("nix-build --out-link /usr/local/nix/state/gcroots/hello")
    if "building '" in result:
        raise RuntimeError(f"unchanged project was rebuilt: {result}")
    guest.command("nix-shell --run 'whatis mk'", native_mk + "/bin/mk")
    guest.command("nix-shell --run 'mk && ./6.out && mk clean'", "hello from nix9")
    guest.command("test ! -e hello.6 && test ! -e 6.out")
    guest.command("echo invalid-c-source > hello.c")
    result = guest.command("nix-build --no-out-link; echo MK-STATUS:$status")
    if not re.search(r"(?m)^MK-STATUS:.*cc9exit=100$", result):
        raise RuntimeError(f"mk failure did not fail the derivation: {result}")
    for file in includes:
        guest.command(f"cat {file}", "host-mkfile-unavailable")
        guest.command(f"unmount /tmp/host-mkfile {file}")
    guest.command("cd /; rm -r /tmp/hello; nix-store --gc")
    guest.command(f"nix-store --verify-path {native_mk}")
    guest.command(f"{package}/bin/hello", "hello from nix9")
    guest.command(f"nix-store --verify-path {package}")
    guest.command(f"rm /usr/local/nix/state/gcroots/hello {mk_root}; nix-store --gc")
    guest.command(f"test ! -e {package}")
    return "native mk, static closure, mkfile build, shell, bundled includes, failures, reuse and GC passed"
