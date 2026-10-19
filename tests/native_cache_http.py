"""Check signed HTTP substitution through webfs and upstream's cache backend."""

import functools
import http.server
from pathlib import Path
import re
import ssl
import threading


class CacheHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = Path(super().translate_path(path))
        relative = path.relative_to(self.directory)
        if relative.parts and relative.parts[0] in ("missing", "truncated"):
            return str(Path(self.directory, "cache", *relative.parts[1:]))
        return str(path)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/server-error/"):
            self.send_error(503)
        elif path.startswith("/redirect/"):
            self.send_response(302)
            self.send_header("Location", "/cache/" + path.removeprefix("/redirect/"))
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path.startswith("/missing/") and path.endswith(".narinfo"):
            self.send_error(404)
        elif path.startswith("/truncated/nar/"):
            data = Path(self.translate_path(self.path)).read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data[:len(data) // 2])
        else:
            super().do_GET()


def check_http_cache(guest, root):
    handler = functools.partial(CacheHandler, directory=root)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, \
            http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / "cert.pem", root / "key.pem")
        tls.socket = context.wrap_socket(tls.socket, server_side=True)
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (server, tls)]
        for thread in threads:
            thread.start()
        try:
            base = f"http://10.0.2.2:{server.server_port}"
            key = (root / "cache.pub").read_text().strip()
            guest.command("previousCache=$cache")
            guest.command(f"key='{key}'")
            guest.command("webfs -m /mnt/web -T 60000")
            guest.command("fn cached { nix-store --option substituters $cache --option trusted-public-keys $key $* }")
            for variant, reason in (("bad-signature", "not signed"), ("bad-content", "hash mismatch"),
                                    ("missing", ""), ("server-error", "503"), ("truncated", "")):
                guest.command(f"cache='{base}/{variant}?store=/usr/local/nix/store'")
                result = guest.command("cached --realise $package; echo HTTP-STATUS:$status")
                if not re.search(r"(?m)^HTTP-STATUS:.*cc9exit=1$", result) or reason not in result:
                    raise RuntimeError(f"HTTP cache accepted {variant}: {result}")
                if variant == "missing" and "webfs request" in result:
                    raise RuntimeError(f"HTTP 404 was treated as a transport failure: {result}")
                guest.command("test ! -e $package && test ! -e $library")
                if re.search(r"(?m)^/usr/local/nix/store/", guest.command("nix-store --dump-db")):
                    raise RuntimeError(f"HTTP {variant} registered a store path")
            guest.command(f"cache='{base}/cache?store=/usr/local/nix/store'")
            guest.command("nix-store --store $cache --check-validity $package")
            guest.command("echo read-only-cache > /tmp/http-upload")
            result = guest.command("nix-store --store $cache --add /tmp/http-upload; echo HTTP-STATUS:$status")
            if not re.search(r"(?m)^HTTP-STATUS:.*cc9exit=1$", result) or "read-only" not in result:
                raise RuntimeError(f"HTTP upload was not rejected: {result}")
            guest.command(f"cache='{base}/redirect?store=/usr/local/nix/store'")
            result = guest.command("cached --realise $package --add-root /usr/local/nix/state/gcroots/http-cache")
            if "copying path" not in result or "building '" in result:
                raise RuntimeError(f"HTTP closure was not substituted: {result}")
            guest.command("nix-store --verify-path $package $library")
            guest.command("chmod +w $package/bin/lua; echo damaged > $package/bin/lua")
            guest.command("cached --repair-path $package")
            guest.command("nix-store --verify-path $package $library")
            guest.command("rm /usr/local/nix/state/gcroots/http-cache; nix-store --gc")
            guest.command(f"cache='https://10.0.2.2:{tls.server_port}/cache?store=/usr/local/nix/store'")
            guest.command("cached --realise $package --add-root /usr/local/nix/state/gcroots/http-cache")
            guest.command("nix-store --verify-path $package $library")
        finally:
            for s in (server, tls):
                s.shutdown()
            for thread in threads:
                thread.join()
    guest.command("cached --realise $package; nix-store --gc")
    guest.command("$package/bin/lua -e 'print(6 * 7)'", "42")
    guest.command("rm /usr/local/nix/state/gcroots/http-cache; nix-store --gc")
    guest.command("test ! -e $package && test ! -e $library")
    guest.command("cache=$previousCache")
    return "HTTP/HTTPS signatures, hashes, missing files, server errors, truncation, redirects, read-only access, repair and offline reuse passed"
