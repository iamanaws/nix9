"""Extract headers and amd64 libraries from the pinned 9front image."""

from pathlib import Path
import sys
import tempfile
import threading

from build_c import ArtifactServer
from guest import boot


def main():
    qemu, disk, output_path = sys.argv[1:]
    output = Path(output_path)
    with tempfile.TemporaryDirectory() as empty, ArtifactServer(empty, output) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://10.0.2.2:{server.server_port}/{output.name}"
        try:
            with boot(qemu, disk) as guest:
                guest.command(
                    "cd / && tar cf /tmp/sysroot.tar sys/include amd64/include amd64/lib"
                )
                guest.command(
                    "size=`{ls -l /tmp/sysroot.tar | awk '{print $6}'}; "
                    f"hget -r 'Content-Length: '^$size -P {url} </tmp/sysroot.tar"
                )
                if not server.received.is_set():
                    raise RuntimeError("guest did not return the sysroot")
        finally:
            server.shutdown()
    print("\nPASS: retrieved headers and libraries from pinned 9front image")


if __name__ == "__main__":
    main()
