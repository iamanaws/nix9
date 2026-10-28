"""Exercise host-bound certificate pins before any HTTP request is sent."""

from contextlib import ExitStack
import http.server
from pathlib import Path
import re
import ssl
import subprocess
import threading
import hashlib
import base64
import socket
import select

from tls import certificate_pin, trust_certificate, reject_certificates


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.requests.append((self.path, self.client_address[1]))
        target = self.server.redirects.get(self.path)
        data = b"" if target else b"TLS trust PASS\n"
        self.send_response(302 if target else 200)
        if target:
            self.send_header("Location", target)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class ProxyHandler(Handler):
    def do_CONNECT(self):
        self.server.requests.append(self.path)
        port = int(self.path.rsplit(":", 1)[1])
        with socket.create_connection(("127.0.0.1", port), timeout=5) as upstream:
            upstream.settimeout(None)
            self.send_response(200)
            self.end_headers()
            self.wfile.flush()
            peers = (self.connection, upstream)
            try:
                while True:
                    ready, _, _ = select.select(peers, [], [], 5)
                    if not ready:
                        return
                    for peer in ready:
                        data = peer.recv(65536)
                        if not data:
                            return
                        (upstream if peer is self.connection else self.connection).sendall(data)
            except (OSError, ssl.SSLError):
                pass
        self.close_connection = True


def certificate(root, name):
    cert, key = root / f"{name}.pem", root / f"{name}.key"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1",
        "-subj", f"/CN={name}", "-addext", f"subjectAltName=DNS:{name}",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return cert, key


def reject(guest, command, reason=None):
    result = guest.command(command + "; echo TLS-STATUS:$status")
    if not re.search(r"(?m)^TLS-STATUS:.+$", result) or (reason and reason not in result):
        raise RuntimeError(f"TLS request did not reject {reason!r}: {result}")


def check_legacy_transport(guest, base):
    digest = base64.b64encode(hashlib.sha256(b"42\n").digest()).decode()
    for scheme in ("http", "https"):
        url = scheme + base[4:] + "/legacy.nix"
        expression = ('builtins.fetchurl { url="' + url + '"; name="legacy-' + scheme
                      + '"; sha256="sha256-' + digest + '"; }')
        reject(guest, f"nix-instantiate --eval --expr '{expression}'", "remount bundled webfs")
    return "legacy webfs refused before HTTP or HTTPS downloads"


def check_tls(guest, root, *, packages=None):
    root = Path(root)
    cert, key = certificate(root, "trusted")
    other_cert, other_key = certificate(root, "other")
    proxy_cert, proxy_key = certificate(root, "proxy")
    policy = "/tmp/nix9-tls-policy"
    mount = "/mnt/nix9-tls"
    with ExitStack() as stack:
        servers = [stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)) for _ in range(3)]
        plain, secure, other = servers
        proxies = [stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)) for _ in range(2)]
        servers += proxies
        for server, pair in ((secure, (cert, key)), (other, (other_cert, other_key)), (proxies[1], (proxy_cert, proxy_key))):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(*pair)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        threads = []
        for server in servers:
            server.requests = []
            server.redirects = {}
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
        try:
            # Local aliases let one certificate be presented under different hosts.
            guest.command("echo 'ip=10.0.2.2 sys=trusted sys=other sys=wrong sys=unknown sys=proxy' >> /lib/ndb/local")
            guest.command("echo -n refresh > /net/cs")
            good = f"https://trusted:{secure.server_port}"
            wrong = f"https://wrong:{secure.server_port}"
            alternate = f"https://other:{other.server_port}"
            plain_url = f"http://trusted:{plain.server_port}"
            pin = trust_certificate(guest, cert, "trusted", directory=policy)
            other_pin = certificate_pin(other_cert)
            guest.command(f"echo '{other_pin}' > {policy}/hosts/wrong")
            guest.command(f"webfs -m {mount} -t {policy} -T 15000")
            guest.command(f"fn tlsGet {{ <> {mount}/clone {{ connection={mount}/^`{{sed 1q}}; echo -n url $1 >[1=0]; cat $connection/body }} }}")
            guest.command(f"tlsGet {good}/warm", "TLS trust PASS")
            guest.command(f"tlsGet {good}/reuse", "TLS trust PASS")
            if secure.requests[-2][1] != secure.requests[-1][1]:
                raise RuntimeError("TLS fixture did not exercise connection reuse")
            guest.command(f"tlsGet https://TRUSTED:{secure.server_port}/case", "TLS trust PASS")
            count = len(secure.requests)
            reject(guest, f"tlsGet {wrong}/wrong-host", "not trusted")
            reject(guest, f"tlsGet https://unknown:{secure.server_port}/unknown-host", "TLS policy")
            if len(secure.requests) != count:
                raise RuntimeError("untrusted TLS connection sent an HTTP request")
            guest.command(f"tlsGet {plain_url}/plain", "TLS trust PASS")
            count = len(plain.requests)
            reject(guest, f"tlsGet https://trusted:{plain.server_port}/plaintext-reuse")
            if len(plain.requests) != count:
                raise RuntimeError("HTTPS reused a plaintext HTTP connection")
            secure.redirects["/relative"] = "/relative-target"
            guest.command(f"tlsGet {good}/relative", "TLS trust PASS")
            plain.redirects["/upgrade"] = good + "/upgraded"
            guest.command(f"tlsGet {plain_url}/upgrade", "TLS trust PASS")
            secure.redirects["/other-host"] = alternate + "/cross-host"
            reject(guest, f"tlsGet {good}/other-host", "TLS policy")
            if other.requests:
                raise RuntimeError("redirect sent a request to an untrusted TLS host")
            guest.command(f"echo '{other_pin}' > {policy}/hosts/other")
            guest.command(f"tlsGet {good}/other-host", "TLS trust PASS")
            secure.redirects["/downgrade"] = plain_url + "/downgraded"
            count = len(plain.requests)
            reject(guest, f"tlsGet {good}/downgrade", "downgrade refused")
            if len(plain.requests) != count:
                raise RuntimeError("HTTPS followed a plaintext redirect")
            # Revocation and pin removal must also reject pooled connections.
            guest.command(f"tlsGet {good}/before-revoke", "TLS trust PASS")
            count = len(secure.requests)
            guest.command(f"echo '{pin}' > {policy}/revoked")
            reject(guest, f"tlsGet {good}/revoked", "revoked")
            if len(secure.requests) != count:
                raise RuntimeError("revoked pooled TLS connection sent a request")
            guest.command(f"tlsGet {alternate}/unrevoked", "TLS trust PASS")
            guest.command(f"echo -n > {policy}/revoked; echo '{pin}' > {policy}/hosts/trusted")
            guest.command(f"tlsGet {good}/before-remove", "TLS trust PASS")
            count = len(secure.requests)
            guest.command(f"echo -n > {policy}/hosts/trusted")
            reject(guest, f"tlsGet {good}/removed", "not trusted")
            if len(secure.requests) != count:
                raise RuntimeError("removed pin remained trusted on a pooled connection")
            guest.command(f"echo '{pin}' > {policy}/hosts/trusted; echo malformed > {policy}/revoked")
            reject(guest, f"tlsGet {good}/malformed", "TLS policy")
            guest.command(f"rm {policy}/revoked")
            reject(guest, f"tlsGet {good}/missing-policy", "TLS policy")
            guest.command(f"echo -n > {policy}/revoked; echo '#include /missing' > {policy}/hosts/trusted")
            reject(guest, f"tlsGet {good}/include", "TLS policy")
            for record in ("x509 sha1=" + "0" * 40,
                           "x509 sha256=" + "0" * 63,
                           "x509 sha256=" + "0" * 63 + "g"):
                guest.command(f"echo '{record}' > {policy}/hosts/trusted")
                reject(guest, f"tlsGet {good}/malformed-pin", "TLS policy")
            guest.command(f"echo '{pin}' > {policy}/hosts/trusted; echo malformed >> {policy}/hosts/trusted")
            reject(guest, f"tlsGet {good}/malformed-after-pin", "TLS policy")
            guest.command(f"awk 'BEGIN {{ for(i=0;i<65537;i++) printf \"x\" }}' > {policy}/hosts/trusted")
            reject(guest, f"tlsGet {good}/oversized-policy", "exceeds 64 KiB")
            guest.command(f"echo '{pin}' > {policy}/hosts/trusted")
            guest.command(f"tlsGet {good}/restored", "TLS trust PASS")
            if packages is not None:
                trust_certificate(guest, cert, "trusted")
                digest = base64.b64encode(hashlib.sha256(b"TLS trust PASS\n").digest()).decode()
                expression = ('{ packages, url, name }: (import (builtins.toPath packages)).fetchurl '
                              '{ inherit url name; hash="sha256-' + digest + '"; }')
                command = (f"nix-build --expr '{expression}' --argstr packages {packages} "
                           f"--argstr url '{good}/native-fetch?tls=@CASE@' --argstr name tls-native-@CASE@ --no-out-link")
                count = len(secure.requests)
                reject_certificates(guest, cert, command, "trusted")
                if len(secure.requests) != count:
                    raise RuntimeError("rejected native fetchurl sent an HTTP request")
                result = guest.command(command.replace("@CASE@", "trusted"))
                paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+-tls-native-trusted$", result)
                if len(paths) != 1:
                    raise RuntimeError(f"native fetchurl did not produce an output: {result}")
                guest.command(f"cat {paths[0]}", "TLS trust PASS")
            proxy_pin = certificate_pin(proxy_cert)
            for scheme, proxy_server in zip(("http", "https"), proxies):
                guest.command(f"unmount {mount}; httpproxy={scheme}://proxy:{proxy_server.server_port} webfs -m {mount} -t {policy} -T 15000")
                if scheme == "https":
                    reject(guest, f"tlsGet {good}/untrusted-proxy", "TLS policy")
                    if proxy_server.requests:
                        raise RuntimeError("untrusted HTTPS proxy received a CONNECT request")
                    guest.command(f"echo '{proxy_pin}' > {policy}/hosts/proxy")
                guest.command(f"tlsGet {good}/through-{scheme}-proxy", "TLS trust PASS")
                if not proxy_server.requests:
                    raise RuntimeError("proxy fixture did not receive a CONNECT request")
                count = len(secure.requests)
                guest.command(f"echo '{pin}' > {policy}/revoked")
                reject(guest, f"tlsGet {good}/revoked-origin-through-proxy", "revoked")
                if len(secure.requests) != count:
                    raise RuntimeError("proxy tunnel reused a revoked origin certificate")
                guest.command(f"echo -n > {policy}/revoked")
                if scheme == "https":
                    guest.command(f"tlsGet {good}/before-proxy-revoke", "TLS trust PASS")
                    count = len(secure.requests)
                    guest.command(f"echo '{proxy_pin}' > {policy}/revoked")
                    reject(guest, f"tlsGet {good}/revoked-proxy", "revoked")
                    if len(secure.requests) != count:
                        raise RuntimeError("pooled connection reused a revoked HTTPS proxy")
                    guest.command(f"echo -n > {policy}/revoked")
            guest.command("rm -f /env/httpproxy")
            guest.command(f"unmount {mount}; fn tlsGet; rm -r {policy}")
        finally:
            for server in servers:
                server.shutdown()
            for thread in threads:
                thread.join()
    return "host pins, unknown/wrong hosts, live revocation/removal, pooled connections, redirect trust, downgrade refusal, HTTP/HTTPS proxy tunnels and policy errors passed"
