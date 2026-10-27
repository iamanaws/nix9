"""Fetch pinned evaluator inputs over webfs and reuse them offline."""

import base64
import functools
import hashlib
import http.server
import json
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading

from eval_tarball import check_eval_tarball, check_large_tarball
from guest import boot


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(self.path)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/eval-source.nix")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/server-error":
            self.send_error(503)
        else:
            super().do_GET()


def check_eval_fetch(guest, root, *, large=False):
    source = b"{ answer = 42; }\n"
    (root / "eval-source.nix").write_bytes(source)
    (root / "eval-fetch.nix").write_text('''
      { url, hash ? null, name ? "eval-source.nix" }:
      let path = builtins.fetchurl ({ inherit url name; }
        // (if hash == null then {} else { sha256 = hash; }));
      in { inherit path; answer = (import path).answer; context = builtins.getContext path; }
    ''')
    digest = base64.b64encode(hashlib.sha256(source).digest()).decode()
    handler = functools.partial(Handler, directory=root)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as plain, \
            http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as secure:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / "cert.pem", root / "key.pem")
        secure.socket = context.wrap_socket(secure.socket, server_side=True)
        servers = (plain, secure)
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
        for server, thread in zip(servers, threads):
            server.requests = []
            thread.start()
        try:
            base = f"http://10.0.2.2:{plain.server_port}"
            guest.command(f"hget -o /tmp/eval-fetch.nix {base}/eval-fetch.nix")
            guest.command("previousEvalCache=$XDG_CACHE_HOME; XDG_CACHE_HOME=/tmp/nix9-eval-fetch-cache")
            guest.command("webfs -m /mnt/web -T 5000")
            guest.command("fn evalFetch { nix-instantiate --eval --strict --json --argstr url $fetchUrl /tmp/eval-fetch.nix $* }")
            guest.command(f"fetchHash='sha256-{digest}'")
            guest.command("wrongFetchHash='sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='")
            guest.command("fn pinnedFetch { evalFetch --argstr hash $fetchHash $* }")
            guest.command(f"fetchUrl={base}/eval-source.nix")
            result = guest.command("pinnedFetch -A path")
            paths = re.findall(r'(?m)^"(/usr/local/nix/store/[^"\n]+)"$', result)
            if len(paths) != 1:
                raise RuntimeError(f"missing evaluator fetch output: {result}")
            path = paths[0]
            guest.command(f"evalSource={path}")
            guest.command("nix-store --realise --add-root /usr/local/nix/state/gcroots/eval-source $evalSource")
            guest.command("pinnedFetch -A answer", "42")
            result = guest.command("pinnedFetch -A context")
            if f'"{path}":{{"path":true}}' not in result:
                raise RuntimeError(f"download lost its string context: {result}")
            guest.command(f"fetchUrl={base}/redirect")
            guest.command("pinnedFetch --argstr name redirect.nix -A answer", "42")
            if "/redirect" not in plain.requests:
                raise RuntimeError("redirect was not fetched")
            guest.command(f"fetchUrl=https://10.0.2.2:{secure.server_port}/eval-source.nix")
            guest.command("pinnedFetch --argstr name https.nix -A answer", "42")
            for endpoint, name, options, reason in (
                ("missing", "missing.nix", "", "404"),
                ("server-error", "error.nix", "", "503"),
                ("eval-source.nix", "wrong.nix", "--argstr hash $wrongFetchHash", "hash mismatch"),
            ):
                guest.command(f"fetchUrl={base}/{endpoint}")
                options = options or "--argstr hash $fetchHash"
                result = guest.command(f"evalFetch --argstr name {name} {options} -A path; echo FETCH-ERROR:$status")
                if reason not in result or not re.search(r"(?m)^FETCH-ERROR:.+$", result):
                    raise RuntimeError(f"evaluator fetch accepted {endpoint}: {result}")
            guest.command(f"fetchUrl={base}/eval-source.nix")
            guest.command("evalFetch -A answer", "42")  # Unpinned URL-cache lookup.
            guest.command("pureFetch='{url, hash ? null}: builtins.fetchurl ({inherit url;} // (if hash == null then {} else {sha256=hash;}))'")
            guest.command("fn pureFetch { nix-instantiate --eval --json --pure-eval --argstr url $fetchUrl --expr $pureFetch $* }")
            guest.command("pureFetch --argstr hash $fetchHash", f'"{path}"')
            result = guest.command("pureFetch; echo FETCH-ERROR:$status")
            if "requires a 'sha256'" not in result or not re.search(r"(?m)^FETCH-ERROR:.+$", result):
                raise RuntimeError(f"pure evaluation accepted an unpinned fetch: {result}")
            check_eval_tarball(guest, root, base, f"https://10.0.2.2:{secure.server_port}")
            if large:
                check_large_tarball(guest, root, base)
        finally:
            for server in servers:
                server.shutdown()
            for thread in threads:
                thread.join()
    # Pinned lookup must work without a fetcher cache or network service.
    guest.command("XDG_CACHE_HOME=/tmp/nix9-eval-fetch-empty-cache; unmount /mnt/web")
    guest.command("pinnedFetch -A answer", "42")
    guest.command("evalTarball -A answer", "42")
    guest.command("pureTarball", "42")
    guest.command("XDG_CACHE_HOME=/tmp/nix9-eval-fetch-cache")
    guest.command("evalFetch -A answer", "42")
    guest.command("nix-store --gc; nix-store --verify-path $evalSource $tarballTree")
    guest.command("rm /usr/local/nix/state/gcroots/eval-source /usr/local/nix/state/gcroots/eval-tree; nix-store --gc")
    guest.command("test ! -e $evalSource && test ! -e $tarballTree")
    guest.command("XDG_CACHE_HOME=$previousEvalCache")
    guest.command("webfs -m /mnt/web -T 60000")
    return "evaluator file/archive fetching, hashes, imports, permissions, unsafe members, pure evaluation, offline reuse and GC passed"


if __name__ == "__main__":
    qemu, image, archive, prefix, output = sys.argv[1:]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(archive, root / "package.tar")
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(root / "key.pem"), "-out", str(root / "cert.pem"),
            "-days", "1", "-subj", "/CN=wrong.example",
            "-addext", "subjectAltName=DNS:wrong.example",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with boot(qemu, image, memory="512M") as guest:
                    guest.child.timeout = 900
                    guest.command(f"cd / && hget http://10.0.2.2:{server.server_port}/package.tar | tar x")
                    guest.command(f". {prefix}/activate")
                    result = check_eval_fetch(guest, root, large=True)
            finally:
                server.shutdown()
                thread.join()
    Path(output).mkdir()
    Path(output, "results.json").write_text(json.dumps({
        "fetching": result, "memory-MiB": 512, "archive-MiB": 640,
    }) + "\n")
