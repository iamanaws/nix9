"""Build libc with upstream mkfiles and link consumers against its archive."""

import re


def check_libc(guest, packages, port):
    for name in ("libc.nix", "libc.c"):
        guest.command(f"hget -o /tmp/{name} http://10.0.2.2:{port}/{name}")
    root = "/usr/local/nix/state/gcroots/libc-tests"
    command = f"nix-build /tmp/libc.nix --argstr packages {packages} -A program --out-link {root}"
    guest.command(command)
    if "building '" in guest.command(command):
        raise RuntimeError("unchanged libc tests were rebuilt")
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-libc-tests$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing libc test output: {result}")
    program = paths[0]
    closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"nix-store -qR {program}")))
    if closure != {program}:
        raise RuntimeError(f"static libc tests retain build dependencies: {closure}")
    guest.command(f"nix-shell /tmp/libc.nix --argstr packages {packages} -A shell --run 'echo native libc shell PASS'", "native libc shell PASS")
    guest.command("nix-store --gc")
    guest.command(f"nix-store --verify-path {program}")
    guest.command(f"{program}/bin/libc-test", "native libc PASS")
    for name in ("strchr", "pow"):
        guest.command(f"{program}/bin/{name}")
    guest.command(f"rm {root}; nix-store --gc")
    guest.command(f"test ! -e {program}")
    return "native libc, upstream mkfiles, input precedence, allocation, Unicode, file syscalls, upstream string/math tests, shell and GC passed"
