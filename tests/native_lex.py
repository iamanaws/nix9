"""Build a scanner/parser with native lex, yacc and the APE scanner runtime."""

import re


def check_lex(guest, packages, port):
    guest.command(f"hget -o /tmp/lex.nix http://10.0.2.2:{port}/lex.nix")
    guest.command("mkdir /tmp/lex")
    for name in ("parser.y", "scanner.l", "mkfile"):
        guest.command(f"hget -o /tmp/lex/{name} http://10.0.2.2:{port}/lex/{name}")
    templates = ("/sys/lib/lex/ncform", "/sys/lib/yaccpar", "/sys/lib/yaccpars")
    guest.command("echo host-template-unavailable > /tmp/no-lex-template")
    for target in templates:
        guest.command(f"bind /tmp/no-lex-template {target}")
    guest.command(f"lexPackages={packages}")
    guest.command("fn lexBuild { nix-build /tmp/lex.nix --argstr packages $lexPackages $* }")
    root = "/usr/local/nix/state/gcroots/lex-parser"
    guest.command(f"lexBuild -A parser --out-link {root}")
    result = guest.command(f"cat {root}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-lex-parser$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing scanner/parser output: {result}")
    parser = paths[0]
    guest.command(f"echo '20 + 22' | {parser}/bin/scanner-parser", "42")
    guest.command(f"echo '3+4+5' | {parser}/bin/scanner-parser", "12")
    result = guest.command(f"echo '2+' | {parser}/bin/scanner-parser; echo PARSER-STATUS:$status")
    if not re.search(r"(?m)^PARSER-STATUS:.+$", result):
        raise RuntimeError(f"parser accepted invalid input: {result}")
    closure = set(re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", guest.command(f"nix-store -qR {parser}")))
    if closure != {parser}:
        raise RuntimeError(f"scanner/parser retains build dependencies: {closure}")
    guest.command("fn lexShell { nix-shell /tmp/lex.nix --argstr packages $lexPackages -A shell --run $* }")
    guest.command("lexShell 'cd /tmp/lex && mk && {echo 20+22 | ./6.out} && lex -t scanner.l > alternate.c && test -s alternate.c && mk clean'", "42")
    result = guest.command("lexBuild -A invalid --no-out-link; echo LEX-STATUS:$status")
    if not re.search(r"(?m)^LEX-STATUS:.*cc9exit=100$", result):
        raise RuntimeError(f"invalid scanner did not fail the build: {result}")
    guest.command("nix-store --gc")
    guest.command(f"nix-store --verify-path {parser}")
    guest.command(f"echo '20+22' | {parser}/bin/scanner-parser", "42")
    for target in templates:
        guest.command(f"cat {target}", "host-template-unavailable")
        guest.command(f"unmount /tmp/no-lex-template {target}")
    guest.command(f"rm {root}; nix-store --gc")
    guest.command(f"test ! -e {parser}")
    return "native lex/yacc, packaged templates, APE libl, mk rules, scanner/parser, shell, invalid scanner and GC passed"
