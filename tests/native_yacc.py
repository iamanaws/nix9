"""Generate and compile a parser with store-provided yacc and mk rules."""

import re


def check_yacc(guest, packages, port):
    guest.command(f"hget -o /tmp/yacc.nix http://10.0.2.2:{port}/yacc.nix")
    guest.command("mkdir /tmp/yacc")
    for name in ("parser.y", "mkfile"):
        guest.command(f"hget -o /tmp/yacc/{name} http://10.0.2.2:{port}/yacc/{name}")
    guest.command("echo host-template-unavailable > /tmp/no-yacc-template")
    for name in ("yaccpar", "yaccpars"):
        guest.command(f"bind /tmp/no-yacc-template /sys/lib/{name}")
    guest.command(f"yaccPackages={packages}")
    guest.command("fn yaccBuild { nix-build /tmp/yacc.nix --argstr packages $yaccPackages $* }")
    root = "/usr/local/nix/state/gcroots/yacc-parser"
    guest.command(f"yaccBuild -A parser --out-link {root}")
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-yacc-parser$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing parser output: {result}")
    parser = paths[0]
    guest.command(f"{parser}/bin/parser '20+22'", "42")
    guest.command(f"{parser}/bin/parser '3+4+5'", "12")
    result = guest.command(f"{parser}/bin/parser '2+'; echo PARSER-STATUS:$status")
    if not re.search(r"(?m)^PARSER-STATUS:.+$", result):
        raise RuntimeError(f"parser accepted invalid input: {result}")
    closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"nix-store -qR {parser}")))
    if closure != {parser}:
        raise RuntimeError(f"generated parser retains build dependencies: {closure}")
    guest.command("fn yaccShell { nix-shell /tmp/yacc.nix --argstr packages $yaccPackages -A shell --run $* }")
    guest.command("yaccShell 'cd /tmp/yacc && mk && ./6.out 20+22 && yacc -S -o alternate.c parser.y && test -s alternate.c && mk clean'", "42")
    result = guest.command("yaccBuild -A invalid --no-out-link; echo YACC-STATUS:$status")
    if not re.search(r"(?m)^YACC-STATUS:.*cc9exit=100$", result):
        raise RuntimeError(f"invalid grammar did not fail the build: {result}")
    guest.command("nix-store --gc")
    guest.command(f"nix-store --verify-path {parser}")
    guest.command(f"{parser}/bin/parser '20+22'", "42")
    for name in ("yaccpar", "yaccpars"):
        guest.command(f"cat /sys/lib/{name}", "host-template-unavailable")
        guest.command(f"unmount /tmp/no-yacc-template /sys/lib/{name}")
    guest.command(f"rm {root}; nix-store --gc")
    guest.command(f"test ! -e {parser}")
    return "native yacc, stored templates, standard mk rules, parser execution, shell, invalid grammar and GC passed"
