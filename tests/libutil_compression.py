"""Check Nix compression against independent host encoders and decoders."""

import gzip
import lzma
import random
import subprocess
import tarfile
import threading

from artifacts import ArtifactServer


def codec(method, data, decode=False):
    if method == "gzip":
        return gzip.decompress(data) if decode else gzip.compress(data, mtime=0)
    if method == "xz":
        return lzma.decompress(data) if decode else lzma.compress(data)
    command = ["brotli" if method == "br" else "zstd", "-c"]
    if decode:
        command.append("-d")
    return subprocess.check_output(command, input=data)


def check_compression(guest, root):
    payloads = {
        "empty": b"",
        "binary": bytes(range(256)) * 513 + b"\0tail",
        "random": random.Random(0).randbytes(65537),
    }
    methods = ("br", "gzip", "xz", "zstd")
    for name, data in payloads.items():
        (root / name).write_bytes(data)
        for method in methods:
            (root / f"{name}.{method}").write_bytes(codec(method, data))
    returned = root / "compression.tar"
    with ArtifactServer(root, returned) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://10.0.2.2:{server.server_port}"
            outputs = []
            for name in payloads:
                # hget does not create an output file for a zero-byte response.
                guest.command(f"echo -n > /tmp/codec-{name}")
                guest.command(f"hget -o /tmp/codec-{name} {url}/{name}")
                for method in methods:
                    fixture = f"{name}.{method}"
                    guest.command(f"hget -o /tmp/{fixture} {url}/{fixture}")
                    guest.command(
                        f"/tmp/libutil-probe compression {method} /tmp/codec-{name} "
                        f"/tmp/{fixture} /tmp/out-{fixture}", "libutil compression PASS")
                    outputs.append(f"out-{fixture}")
            guest.command("cd /tmp && tar cf compression.tar " + " ".join(outputs))
            guest.command(
                "size=`{ls -l /tmp/compression.tar | awk '{print $6}'}; "
                f"hget -r 'Content-Length: '^$size -P {url}/compression.tar </tmp/compression.tar")
            if not server.received.is_set():
                raise RuntimeError("missing guest compression output")
            with tarfile.open(returned) as archive:
                for name, data in payloads.items():
                    for method in methods:
                        encoded = archive.extractfile(f"out-{name}.{method}").read()
                        if codec(method, encoded, decode=True) != data:
                            raise RuntimeError(f"host could not decode {name}.{method}")
        finally:
            server.shutdown()
            thread.join()
    return {"methods": methods, "cases": len(payloads) * len(methods)}
