"""Provision the development inventory with normal native installation commands."""

from contextlib import contextmanager
import functools
import http.server
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading

from boot_medium import boot_medium


ROOTS = "/usr/local/nix/state/gcroots"
CPUS = ("build", "batch")
MACHINES = ("auth", "files", *CPUS)
ADDRESSES = {name: f"10.0.2.{100 + index}" for index, name in enumerate(MACHINES)}


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def store_path(guest, command):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", guest.command(command))
    if len(paths) != 1:
        raise RuntimeError(f"expected one store path: {command}: {paths}")
    return paths[0]


def nvram(key):
    fields = (bytes(7), bytes(7), bytes(14), b"glenda".ljust(28, b"\0"),
              b"nix9.netroot".ljust(48, b"\0"), key)
    return b"".join(value + bytes([(9 + sum(value)) % 256]) for value in fields)


def disk(qemu, destination, backing):
    if destination.exists():
        raise RuntimeError(f"refusing to replace {destination}")
    subprocess.run([str(Path(qemu).with_name("qemu-img")), "create", "-f", "qcow2", "-F", "qcow2",
                    "-b", str(backing), str(destination)], check=True)


@contextmanager
def transfers(directory):
    token = secrets.token_urlsafe(24)

    class Transfer(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if not self.path.startswith("/" + token + "/"):
                self.send_error(404)
                return
            self.path = self.path[len(token) + 1:]
            super().do_GET()

    handler = functools.partial(Transfer, directory=directory)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def download(guest, name, destination=None, private=False):
                destination = destination or "/tmp/" + name
                if private:
                    guest.command(f"echo -n > {destination}; chmod 600 {destination}")
                guest.command(f"hget -o {destination} http://10.0.2.2:{server.server_port}/{token}/{name}")
            yield download
        finally:
            server.shutdown()
            thread.join()


def provision(lab):
    work = lab.work
    keys = {name: secrets.token_bytes(16) for name in ("glenda", "alice", "bob", "builder", "files", *CPUS)}
    transfer = work / "provision"
    transfer.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__).with_name("configuration.nix"), work / "configuration.nix")
    shutil.copyfile(work / "configuration.nix", transfer / "configuration.nix")
    for name, key in keys.items():
        roles = ("server", "speakfor") if name in CPUS else ("server",) if name == "files" else ("client",)
        (transfer / (name + ".keys")).write_text("".join(
            f"key proto=dp9ik dom=nix9.netroot user={name} role={role} !hex={key.hex()} !password=______\n"
            for role in roles))
        (transfer / (name + ".aes")).write_bytes(key)
    (transfer / "server.nvram").write_bytes(nvram(keys["glenda"]))
    (transfer / "cwfs.setup").write_text("service files\nconfig /adm/storage/config\n"
                                         "filsys main cw0fw1\nfilsys dump o\nream main\nend\n")
    with transfers(transfer) as download:
        lab.progress("Installing the bootstrap and preparing native server packages...")
        foundation = work / "bootstrap.qcow2"
        disk(lab.qemu, foundation, work / "roots/image/9front.qcow2")
        with lab.machine("bootstrap", disk=foundation, provisioning=True) as guest:
            guest.command("cp /dev/sdG0/data /tmp/bootstrap.tar")
            guest.command("cd / && tar xf /tmp/bootstrap.tar")
            guest.command(". /usr/local/pkg/nix9/activate")
            guest.command("nix-build '<nix9>' -A cwfs -A auth -A rcpu -A ndb --out-link " + ROOTS + "/lab-tools")
        for name, size in (("cache", 3), ("worm", 8)):
            with (work / (name + ".raw")).open("xb") as file:
                file.truncate(size * 1024**3)
        for name in ("auth", "files"):
            lab.progress(f"Provisioning {name}...")
            disk(lab.qemu, work / (name + ".qcow2"), foundation)
            with lab.machine(name, provisioning=True) as guest:
                guest.command(". /usr/local/pkg/nix9/activate && nix9 init " + name)
                download(guest, "server.nvram", private=True)
                guest.command("dd -if /tmp/server.nvram -of /dev/sdF0/nvram -bs 126 -count 1; rm /tmp/server.nvram")
                guest.command("mkdir -p /cfg/nix9-lab")
                download(guest, "configuration.nix", "/cfg/nix9-lab/default.nix")
                if name == "auth":
                    guest.command("rm /adm/keys; auth/keyfs -m /mnt/keys /adm/keys")
                    for identity in keys:
                        download(guest, identity + ".aes", private=True)
                        guest.command(f"mkdir /mnt/keys/{identity}; cp /tmp/{identity}.aes /mnt/keys/{identity}/aeskey; rm /tmp/{identity}.aes")
                    for identity in ("glenda", "alice", "bob"):
                        download(guest, identity + ".keys", "/adm/" + identity + ".keys", private=True)
                else:
                    download(guest, "files.keys", "/adm/files.keys", private=True)
                    download(guest, "glenda.keys", "/adm/lab-client.keys", private=True)
                    for cpu in CPUS:
                        download(guest, cpu + ".keys", private=True)
                    download(guest, "builder.keys", private=True)
                    guest.command("mkdir /adm/storage; chmod 700 /adm/storage")
                    guest.command("dd -if /dev/zero -of /adm/storage/config -bs 16384 -count 1; chmod 600 /adm/storage/config")
                    download(guest, "cwfs.setup")
                    guest.command("echo 'w0 /dev/sdG0/data' > /tmp/devices; echo 'w1 /dev/sdH0/data' >> /tmp/devices")
                    guest.command(f"cwfs=`{{cat {ROOTS}/lab-tools}}; fsmempercent=5 $cwfs/bin/cwfs64x "
                                  "-c -f /adm/storage/config -m /tmp/devices -n provision < /tmp/cwfs.setup")
                    for command in ("users default", "create /adm adm adm 775 d", "create /adm/users adm adm 664",
                                    "create /usr adm adm 775 d", "newuser glenda", "create /systems glenda glenda 775 d",
                                    "create /machines glenda glenda 775 d"):
                        guest.command("echo " + quote(command) + " >> /srv/provision.cmd")
                    guest.command("echo halt >> /srv/provision.cmd; while(test -e /srv/provision.cmd) sleep 1; status=''")
                    guest.command("nix-build /cfg/nix9-lab/default.nix -A build --out-link " + ROOTS + "/lab-installation")
                system = store_path(guest, f"nix-build /cfg/nix9-lab/default.nix -A systems.{name} --no-out-link")
                guest.command("nix9 select " + system)
                guest.command("9fs 9fat; echo 'service=cpu' >> /n/9fat/plan9.ini; echo 'init=/amd64/init -c' >> /n/9fat/plan9.ini")
        lab.start("auth")
        files = lab.start("files")
        files.command("cat /adm/lab-client.keys > /mnt/factotum/ctl && mount -c /srv/cwfs-nix9 /n/site main")
        files.command("installation=`{cat " + ROOTS + "/lab-installation}; root=`{cat $installation/roots/stable}")
        lab.progress("Publishing the shared OS root...")
        files.command("rc $root/publish /n/site")
        for name in CPUS:
            lab.progress(f"Preparing {name} and selecting its first system...")
            artifact = store_path(files, "cat $installation/boot/" + name + "/path")
            files.command("rc " + artifact + "/prepare /n/site /tmp/bootstrap.tar $installation/systems/" + name)
            files.command(f"cp /tmp/{name}.keys /n/site/machines/{name}/adm/cpu.keys; chmod 600 /n/site/machines/{name}/adm/cpu.keys")
            if name == "build":
                files.command("cp /tmp/builder.keys /n/site/machines/build/adm/builder.keys; "
                              "chmod 600 /n/site/machines/build/adm/builder.keys")
            settings = files.command("cat " + artifact + "/plan9.ini")
            configuration = "\n".join(line for line in settings.splitlines() if re.match(r"^[a-z0-9]+=", line)) + "\n"
            boot_medium(lab.qemu, work / "roots/image/9front.qcow2", work / (name + ".qcow2"),
                        configuration, nvram(keys["glenda"]))
            with lab.machine(name) as cpu:
                cpu.command(". /usr/local/pkg/nix9/activate")
                cpu.command("rc /cfg/nix9/initial/finish")
            lab.start(name)
        lab.progress("Preparing the shared C project...")
        auth = lab.guests["auth"]
        auth.command("rcpu -u alice -h build -c 'mkdir -p /n/projects/hello && "
                     "cp $nix9/packages/examples/workstation/project/* /n/projects/hello/ && "
                     "chmod 770 /n/projects/hello && chmod 660 /n/projects/hello/*'")
    shutil.rmtree(transfer)
