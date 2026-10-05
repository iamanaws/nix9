"""Fetch Lua over HTTPS, then build its library and interpreter inside 9front."""

from contextlib import contextmanager
import functools
import http.server
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import threading

from lua import EXPECTED


@contextmanager
def source_server(root, archive):
    shutil.copyfile(archive, root / "lua-5.4.8.tar.gz")
    for name in ("sources.nix", "isolation.nix", "lua/check.lua", "lua/fixture.lua"):
        shutil.copyfile(Path(__file__).parent / name, root / Path(name).name)
    # Deliberately untrusted and for a different host: webfs currently accepts it.
    key, cert = root / "key.pem", root / "cert.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "1",
                    "-subj", "/CN=wrong.example", "-addext", "subjectAltName=DNS:wrong.example"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join()


def check_sources(guest, prefix, http_port, tls_port):
    base = f"http://10.0.2.2:{http_port}"
    guest.command("mkdir /tmp/lua")
    guest.command(f"hget -o /tmp/sources.nix {base}/sources.nix")
    guest.command(f"hget -o /tmp/isolation.nix {base}/isolation.nix")
    directories = ("/amd64/bin", "/rc/bin", "/rc/lib", "/sys/include", "/amd64/include", "/amd64/lib")
    for directory in directories:
        guest.command(f"echo host-only > {directory}/nix9-host-only")
    guest.command("isolation=`{nix-instantiate /tmp/isolation.nix --argstr packages $fetchPackages}")
    guest.command("isolated=`{nix-store --realise $isolation}; cat $isolated", "namespace-isolated")
    for name in ("check.lua", "fixture.lua"):
        guest.command(f"hget -o /tmp/lua/{name} {base}/{name}")
    guest.command(f"luaUrl=https://10.0.2.2:{tls_port}/lua-5.4.8.tar.gz")
    guest.command("luaDrv=`{nix-instantiate /tmp/sources.nix --argstr packages $fetchPackages --argstr url $luaUrl}")
    guest.command("nix-store --realise $luaDrv --add-root /usr/local/nix/state/gcroots/lua")
    result = guest.command("cat /usr/local/nix/state/gcroots/lua")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-lua-5\.4\.8$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing native Lua output: {result}")
    package = paths[0]
    result = guest.command(f"nix-store -q --references {package}")
    libraries = re.findall(r"(?m)^/usr/local/nix/store/[a-z0-9]{32}-liblua-5\.4\.8$", result)
    if len(libraries) != 1:
        raise RuntimeError(f"Lua does not retain its library: {result}")
    library = libraries[0]
    # Builder namespace changes must not leak into the store client or parent shell.
    for directory in directories:
        guest.command(f"cat {directory}/nix9-host-only", "host-only")
        guest.command(f"rm {directory}/nix9-host-only")
    guest.command(f"test -s {library}/lib/liblua.a && test -s {library}/include/lua.h")
    guest.command(f"lua={package}/bin/lua")
    guest.command("mkdir /tmp/lua-work && cd /tmp/lua-work")
    result = guest.command("$lua /tmp/lua/check.lua 23")
    passed = [line for line in result.splitlines() if line.startswith("PASS:")]
    if passed != EXPECTED:
        raise RuntimeError(f"native Lua checks failed: {passed!r}")
    result = guest.command("$lua -e 'print(package.path)'")
    if f"{library}/share/lua/5.4/?.lua" not in result:
        raise RuntimeError(f"Lua module search path does not use its library: {result}")
    guest.command("cd /")
    guest.command(f"publicLua=`{{nix-instantiate --expr '(import {prefix}/share/nix9).lua'}}")
    result = guest.command("nix-store --realise $publicLua", package)
    if "building '" in result:
        raise RuntimeError(f"public Lua did not reuse the pinned source build: {result}")
    guest.command("nix-store --gc")
    guest.command(f"nix-store --verify-path {package} {library}")
    # TLS transport does not replace Nix's required content hash.
    guest.command("fetchHash='sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='")
    guest.command(f"fetchUrl=https://10.0.2.2:{tls_port}/hello.c")
    guest.command("badDrv=`{instantiateFetch source}")
    result = guest.command("if(nix-store --realise $badDrv) {echo unexpected-success}; "
                           "if not {echo rejected}", "rejected")
    if "hash mismatch" not in result:
        raise RuntimeError(f"HTTPS did not reach hash verification: {result}")
    guest.command("badOut=`{nix-store -q --outputs $badDrv}; test ! -e $badOut")
    return {"package": package, "library": library, "https": "passed", "archive-build": "passed",
            "lua-checks": len(EXPECTED), "certificate-validation": "unsupported (untrusted, wrong host accepted)",
            "https-hash-mismatch": "passed", "toolchain-isolation": "passed"}
