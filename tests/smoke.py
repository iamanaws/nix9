"""Execute a host-provided program in a fresh 9front snapshot."""

import functools
import http.server
from pathlib import Path
import sys
import threading

from guest import boot


def main():
    qemu, disk, binary, expected = sys.argv[1:]
    binary = Path(binary)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(binary.parent)
    )
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with boot(qemu, disk) as guest:
                guest.command(
                    f"hget -o /tmp/program http://10.0.2.2:{server.server_port}/{binary.name}"
                )
                guest.command("chmod +x /tmp/program")
                guest.command("/tmp/program", expected=expected)
        finally:
            server.shutdown()
    print("\nPASS: Nix-built executable ran inside 9front")


if __name__ == "__main__":
    main()
