"""Transfer fixtures and test artifacts between the host and a disposable guest."""

import functools
import http.server
import threading


class ArtifactServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, source, output):
        super().__init__(
            ("127.0.0.1", 0), functools.partial(Handler, directory=source)
        )
        self.output = output
        self.received = threading.Event()


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        # The guest supplies a length explicitly; accept only this artifact.
        if self.path != "/" + self.server.output.name or self.headers.get("Transfer-Encoding"):
            self.send_error(400)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if not 40 <= length <= 128 * 1024 * 1024:
            self.send_error(400)
            return
        self.connection.settimeout(30)
        data = self.rfile.read(length)
        if len(data) != length:
            self.send_error(400)
            return
        self.server.output.write_bytes(data)
        self.server.received.set()
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()
