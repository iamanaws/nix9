"""Make private kernel/9fat/NVRAM media from the pinned VM, without its OS filesystem."""

from pathlib import Path
import re
import struct
import subprocess


def boot_medium(qemu, image, destination, configuration, nvram):
    destination = Path(destination)
    if destination.exists():
        raise RuntimeError(f"refusing to replace {destination}")
    qemu_img = str(Path(qemu).with_name("qemu-img"))
    header = destination.with_suffix(".header")
    raw = destination.with_suffix(".raw")
    ini = destination.with_suffix(".ini")
    subprocess.run([qemu_img, "dd", "-f", "qcow2", f"if={image}", f"of={header}", "bs=512", "count=256"], check=True)
    data = header.read_bytes()
    entries = [446 + 16 * index for index in range(4) if data[446 + 16 * index + 4] == 0x39]
    if len(entries) != 1:
        raise RuntimeError("expected one Plan 9 partition")
    entry = entries[0]
    start, _ = struct.unpack_from("<II", data, entry + 8)
    table = data[(start + 1) * 512:(start + 2) * 512].split(b"\0", 1)[0].decode()
    parts = {name: (int(first), int(last)) for name, first, last in re.findall(r"part (\S+) (\d+) (\d+)", table)}
    retained = {name: parts[name] for name in ("9fat", "nvram")}
    sectors = start + max(last for _, last in retained.values())
    subprocess.run([qemu_img, "dd", "-f", "qcow2", f"if={image}", f"of={raw}", "bs=512", f"count={sectors}"], check=True)
    with raw.open("r+b") as file:
        file.seek(entry + 12)
        file.write(struct.pack("<I", sectors - start))
        table = "".join(f"part {name} {first} {last}\n" for name, (first, last) in retained.items()).encode()
        file.seek((start + 1) * 512)
        file.write(table.ljust(512, b"\0"))
        file.seek((start + parts["nvram"][0]) * 512)
        file.write(nvram)
    medium = f"{raw}@@{(start + parts['9fat'][0]) * 512}"
    original = subprocess.check_output(["mtype", "-i", medium, "::plan9.ini"], text=True)
    keys = {line.split("=", 1)[0] for line in configuration.splitlines() if "=" in line}
    lines = [line for line in original.splitlines() if line.split("=", 1)[0] not in keys]
    ini.write_text("\n".join(lines) + "\n" + configuration)
    subprocess.run(["mcopy", "-o", "-i", medium, str(ini), "::plan9.ini"], check=True)
    subprocess.run([qemu_img, "convert", "-f", "raw", "-O", "qcow2", str(raw), str(destination)], check=True)
    destination.chmod(0o600)
    for file in (header, raw, ini):
        file.unlink()
    return sectors * 512
