"""Fetch source through native webfs, then compile it with a native derivation."""

import base64
import hashlib
from pathlib import Path
import re


SOURCE = b'#include <u.h>\n#include <libc.h>\nvoid main(void) { print("fetched source PASS\\n"); exits(nil); }\n'


def fetch_fixtures(root):
    (root / "hello.c").write_bytes(SOURCE)
    (root / "source").mkdir()
    (root / "source" / "index.html").write_bytes(SOURCE)
    (root / "fetch.nix").write_bytes(Path(__file__).with_name("fetch.nix").read_bytes())


def check_fetch(guest, prefix, port):
    url = f"http://10.0.2.2:{port}"
    guest.command(f"hget -o /tmp/fetch.nix {url}/fetch.nix")
    guest.command(f"fetchPackages={prefix}/share/nix9")
    digest = base64.b64encode(hashlib.sha256(SOURCE).digest()).decode()
    guest.command(f"fetchHash='sha256-{digest}'")
    guest.command(f"fetchUrl={url}/source")
    guest.command("fn instantiateFetch { nix-instantiate /tmp/fetch.nix --argstr packages $fetchPackages "
                  "--argstr url $fetchUrl --argstr hash $fetchHash -A $1 }")
    guest.command("fetchDrv=`{instantiateFetch hello}")
    result = guest.command("nix-store --realise $fetchDrv")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-fetched-hello$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing fetched build: {result}")
    guest.command(paths[0], "fetched source PASS")
    guest.command("sourceDrv=`{instantiateFetch source}")
    result = guest.command("nix-store --realise $sourceDrv")
    source = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-hello.c$", result)[0]
    guest.command(f"nix-store --verify-path {source}")
    # A different URL must reuse the verified fixed output, without fetching.
    guest.command(f"fetchUrl={url}/missing")
    guest.command("reuseDrv=`{instantiateFetch source}")
    guest.command("nix-store --realise $reuseDrv", source)
    guest.command("fetchHash='sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='")
    for endpoint in ("hello.c", "missing"):
        guest.command(f"fetchUrl={url}/{endpoint}")
        guest.command("badDrv=`{instantiateFetch source}")
        guest.command("badOut=`{nix-store -q --outputs $badDrv}")
        guest.command("if(nix-store --realise $badDrv) {echo unexpected-success}; "
                      "if not {echo rejected}", "rejected")
        guest.command("test ! -e $badOut")
        guest.command("if(nix-store --check-validity $badOut) {echo unexpected-valid}; "
                      "if not {echo invalid}", "invalid")
    return {"source-build": "passed", "redirect": "passed", "reuse": "passed", "hash-mismatch": "passed", "http-error": "passed"}
