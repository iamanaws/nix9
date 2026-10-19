"""Build a standalone project and check its explicit GC root."""

import re


def check_project(guest, port):
    guest.command("mkdir /tmp/hello")
    for name in ("default.nix", "shell.nix", "hello.c"):
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
    guest.command("nix-build shell.nix --out-link /usr/local/nix/state/gcroots/hello-shell")
    guest.command("development=`{cat /usr/local/nix/state/gcroots/hello-shell}")
    guest.command("$development/shell -c '6c -o hello.6 hello.c && 6l -o hello hello.6 && ./hello'", "hello from nix9")
    guest.command("rm /usr/local/nix/state/gcroots/hello-shell")
    guest.command("cd /; rm -r /tmp/hello; nix-store --gc")
    guest.command(f"{package}/bin/hello", "hello from nix9")
    guest.command(f"nix-store --verify-path {package}")
    guest.command("rm /usr/local/nix/state/gcroots/hello; nix-store --gc")
    guest.command(f"test ! -e {package}")
    return "standalone build, reuse and garbage collection passed"
