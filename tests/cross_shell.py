"""Run programs built in the Linux cross-development shell."""

import functools
import http.server
import json
from pathlib import Path
import sys
import threading

from guest import boot


qemu, image, programs, output = sys.argv[1:]
expected = {
    "hello": "hello from nix9",
    "edited": "hello from cross shell",
    "direct": "hello from cross shell",
    "ape": "cross shell APE PASS",
    "inputs": "cross stdenv PASS",
}
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=programs)
with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with boot(qemu, image) as guest:
            for name, message in expected.items():
                guest.command(f"hget -o /tmp/{name} http://10.0.2.2:{server.server_port}/{name}")
                guest.command(f"chmod +x /tmp/{name}; /tmp/{name}", message)
    finally:
        server.shutdown()
Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({name: "passed" for name in expected}) + "\n")
