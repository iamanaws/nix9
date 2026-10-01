"""Compile C in the pinned guest and retrieve its executable into a Nix output."""

import functools
import http.server
from pathlib import Path
import sys
import threading

from guest import boot


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


def main():
    qemu, disk, source, output_dir = sys.argv[1:]
    output = Path(output_dir) / "bin" / "hello-c"
    output.parent.mkdir(parents=True)
    with ArtifactServer(source, output) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://10.0.2.2:{server.server_port}"
        try:
            with boot(qemu, disk) as guest:
                guest.command(f"hget -o /tmp/hello.c {url}/main.c")
                guest.command("cd /tmp && 6c -o hello.6 hello.c")
                guest.command("cd /tmp && 6l -o hello-c hello.6")
                guest.command(
                    "/tmp/hello-c",
                    expected="Hello from Nix-built C on 9front/amd64!",
                )
                guest.command(
                    "size=`{ls -l /tmp/hello-c | awk '{print $6}'}; "
                    f"hget -r 'Content-Length: '^$size -P {url}/hello-c </tmp/hello-c"
                )
                if not server.received.is_set():
                    raise RuntimeError("guest did not return the executable")
        finally:
            server.shutdown()
    output.chmod(0o755)
    print("\nPASS: built, executed, and retrieved native 9front C package")


if __name__ == "__main__":
    main()
