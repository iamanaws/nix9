"""Extract selected directories from the pinned 9front image."""

from pathlib import Path
import sys
import tempfile
import threading

from build_c import ArtifactServer
from guest import boot


def export_tree(qemu, disk, output_path, paths, prepare=()):
    if not paths:
        raise ValueError("at least one guest directory is required")
    output = Path(output_path)
    with tempfile.TemporaryDirectory() as empty, ArtifactServer(empty, output) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://10.0.2.2:{server.server_port}/{output.name}"
        try:
            with boot(qemu, disk) as guest:
                members = " ".join("'" + path.replace("'", "''") + "'" for path in paths)
                for command in prepare:
                    guest.command(command)
                guest.command("cd / && tar cf /tmp/export.tar " + members)
                guest.command(
                    "size=`{ls -l /tmp/export.tar | awk '{print $6}'}; "
                    f"hget -r 'Content-Length: '^$size -P {url} </tmp/export.tar"
                )
                if not server.received.is_set():
                    raise RuntimeError("guest did not return the archive")
        finally:
            server.shutdown()
    print("\nPASS: retrieved directories from pinned 9front image")


if __name__ == "__main__":
    qemu, disk, output_path, *paths = sys.argv[1:]
    export_tree(qemu, disk, output_path, paths)
