"""Backup failures and recovery onto a separately provisioned CWFS volume."""

from pathlib import Path
import re
import time


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def snapshot_key(path):
    year, name = path.rsplit("/", 2)[-2:]
    return int(year), int(name[:4]), int(name[4:] or "0")


def check_backups(*, work, stack, terminal, auth, files, backup, builders,
                  systems, snapshot, start, stop, built, disks,
                  listening, rejected):
    repository = "/usr/glenda/archives/projects"
    job = "projects-backup"
    root = "/usr/local/nix/state/gcroots"
    run = "rc $nix9System/services/backups/projects/run"

    def remote(name, command, expected=None):
        return terminal.command("rcpu -h " + name + " -c " + quote(command), expected)

    def completed():
        listing = backup.command(f"ls -d {repository}/* >[2]/dev/null; status=''")
        return re.findall(re.escape(repository) + r"/[0-9]+-[0-9]+(?=\n|$)", listing)

    # Exercise names, metadata and a zero-length file as well as project sources.
    terminal.command("mkdir /usr/glenda/work/nested; echo spaced-name > '/usr/glenda/work/nested/a file'")
    terminal.command("echo -n > /usr/glenda/work/nested/empty; chmod 640 /usr/glenda/work/hello.c")
    terminal.command("disk/checksum /usr/glenda/work/nested/empty", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    files.command("echo dump >> /srv/cwfs-nix9.cmd")
    deadline = time.monotonic() + 40
    while True:
        listing = terminal.command("ls -d /n/history/*/* >[2]/dev/null; status=''")
        snapshots = re.findall(r"(?m)^/n/history/[0-9]{4}/[0-9]{4,}$", listing)
        newer = [p for p in snapshots if p != snapshot]
        if newer:
            snapshot = max(newer, key=snapshot_key)
            if "spaced-name" in terminal.command("cat " + snapshot + "/projects/nested/'a file' >[2]/dev/null; status=''"):
                break
        if time.monotonic() > deadline:
            raise RuntimeError("new completed snapshot did not appear")
        time.sleep(0.2)

    # Change main after the dump: the archive must retain the historical content.
    terminal.command("echo live-change > /usr/glenda/work/nested/'a file'")
    table = auth.command("cat " + systems["auth"] + "/services/cron/tables/glenda")
    dispatchers = re.findall(r"/usr/local/nix/store/\S+-nix9-job-projects-backup.remote/run", table)
    if len(dispatchers) != 1:
        raise RuntimeError("missing remote backup dispatcher")
    dispatcher = dispatchers[0]
    try:
        auth.command(". /usr/local/pkg/nix9/system; rc " + dispatcher)
    except Exception:
        builders["build"].command("cat /sys/log/nix9-jobs/glenda/projects-backup.log; status=''")
        auth.command("cat /sys/log/nix9-jobs/glenda/projects-backup.remote.log; status=''")
        raise
    first = completed()
    if len(first) != 1:
        raise RuntimeError(f"missing completed backup: {first}")
    generation = first[0]
    backup.command(f"ls -ld {generation} | awk '{{print $1}}'", "d-rwx------")
    backup.command(f"ls -l {generation} | awk '$1 != \"--rw-------\" {{bad=1}} END {{exit bad}}'")
    backup.command(f"grep -s 'snapshot {snapshot}$' {generation}/source")
    auth.command(f"grep -s 'status=$' /sys/log/nix9-jobs/glenda/{job}.remote.log")
    builders["build"].command(f"grep -s 'nix9-backup: completed' /sys/log/nix9-jobs/glenda/{job}.log")
    print("PASS: authenticated remote scheduled job archives a completed snapshot onto independent TLS storage", flush=True)

    # A second run retains both references. An existing lock prevents overlap.
    remote("build", run)
    if len(completed()) != 2:
        raise RuntimeError("a second backup replaced the first")
    backup.command(f"mkdir {repository}/lock")
    rejected(terminal, "rcpu -h build -c " + quote(run), "another backup holds the lock")
    backup.command(f"test -d {repository}/lock; rm {repository}/lock")
    if len(completed()) != 2:
        raise RuntimeError("an overlapping run published an archive")

    # A local directory bound over the destination must not receive an archive.
    command = "@{ rfork ne; bind /tmp /n/archives; " + run + " }"
    rejected(terminal, "rcpu -h build -c " + quote(command), "managed mount was changed")
    if len(completed()) != 2:
        raise RuntimeError("a missing managed mount published an archive")

    connections = files.command("netstat -n")
    source_connections = len(re.findall(r"(?m)^tcp\s+\d+\s+\S+\s+Established\s+564\s", connections))
    stop(backup)
    rejected(terminal, "rcpu -h build -c " + quote(run), "managed mount is unavailable: archives")
    builders["build"].command("test ! -e /n/archives/projects")
    backup = stack.enter_context(start("backup"))
    listening(backup, 17021)
    stop(terminal)
    terminal = stack.enter_context(start("terminal"))
    terminal.command(". /usr/local/pkg/nix9/system")
    if len(completed()) != 2:
        raise RuntimeError("backup provider loss changed completed generations")

    # An unreadable file makes the whole archive fail and leaves no completed reference.
    terminal.command("echo private > /usr/glenda/work/blocked; chmod 000 /usr/glenda/work/blocked")
    files.command("echo dump >> /srv/cwfs-nix9.cmd")
    deadline = time.monotonic() + 30
    while True:
        listing = terminal.command("ls -d /n/history/*/* >[2]/dev/null; status=''")
        snapshots = re.findall(r"(?m)^/n/history/[0-9]{4}/[0-9]{4,}$", listing)
        latest = max(snapshots, key=snapshot_key)
        if "SNAPSHOT-READY" in terminal.command("if(test -e " + latest + "/projects/blocked) echo SNAPSHOT-READY; status=''"):
            break
        if time.monotonic() > deadline:
            raise RuntimeError("unreadable-file snapshot did not appear")
        time.sleep(0.2)
    rejected(terminal, "rcpu -h build -c " + quote(run), "archive creation failed")
    backup.command(f"test ! -e {repository}/lock")
    if len(completed()) != 2:
        raise RuntimeError("a skipped source file published a partial archive")

    # Reject incomplete archives and checksum corruption before writing to a restore root.
    terminal.command("mkdir /tmp/restore-empty; mkdir /tmp/bad-backup")
    terminal.command(f"cp /n/archives/projects/{Path(generation).name}/sha256 /tmp/bad-backup/sha256")
    terminal.command("echo damaged > /tmp/bad-backup/archive")
    rejected(terminal, "disk/restore /tmp/bad-backup /tmp/restore-empty", "checksum")
    terminal.command("ls /tmp/restore-empty | wc -l | awk '{print $1}'", "0")
    terminal.command("echo '/projects/file 640 glenda glenda 1 8' > /tmp/bad-backup/archive; echo -n short >> /tmp/bad-backup/archive")
    rejected(terminal, "disk/mkext -h < /tmp/bad-backup/archive", "premature eof")
    terminal.command("disk/checksum /tmp/bad-backup/archive > /tmp/bad-backup/sha256")
    rejected(terminal, "disk/restore /tmp/bad-backup /tmp/restore-empty", "archive validation")
    terminal.command("ls /tmp/restore-empty | wc -l | awk '{print $1}'", "0")
    print("PASS: completed generations retained, overlap excluded, provider loss, unreadable sources and corrupt archives rejected", flush=True)

    # The old disks remain offline throughout restoration and the two CPU builds.
    stop(terminal)
    stop(files)
    original = disks["files"]
    disks["files"] = work / "replacement.qcow2"
    replacement = stack.enter_context(start("files"))
    listening(replacement, 564)
    terminal = stack.enter_context(start("terminal"))
    terminal.command(". /usr/local/pkg/nix9/system")
    terminal.command("test ! -e /usr/glenda/work/default.nix; test ! -e /usr/glenda/work/hello.c")
    terminal.command("ls /n/history | wc -l | awk '{print $1}'", "0")
    terminal.command("disk/restore /n/archives/projects/" + Path(generation).name + " /n/work")
    terminal.command("cat /usr/glenda/work/nested/'a file'", "spaced-name")
    terminal.command("test ! -s /usr/glenda/work/nested/empty")
    terminal.command("ls -l /usr/glenda/work/hello.c | awk '{print $1, $4, $5}'", "--rw-r----- glenda glenda")
    restored = {}
    # Force a new build on both independent stores from the recovered workspace.
    terminal.command("sed 's/storage-original/storage-recovered/' /usr/glenda/work/hello.c > /tmp/recovered.c; cp /tmp/recovered.c /usr/glenda/work/hello.c")
    for name in builders:
        terminal.command("rcpu -h " + name + " -c " + quote("nix-build /usr/glenda/work --out-link " + root + "/workspace"))
        output = builders[name].command("cat " + root + "/workspace")
        paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", output)
        if len(paths) != 1 or paths[0] == built[name]:
            raise RuntimeError("recovered workspace did not produce a new build")
        terminal.command("rcpu -h " + name + " -c " + quote(paths[0] + "/bin/storage-project"), "storage-recovered")
        restored[name] = paths[0]
    if len(set(restored.values())) != 1:
        raise RuntimeError("the CPU stores disagreed on the recovered build")
    print("PASS: original file server offline, fresh CWFS volume restored, both CPU servers build the recovered project", flush=True)
    return {"status": "passed", "generations": completed(), "snapshot": snapshot,
            "sourceConnectionsBeforeOutage": source_connections,
            "originalDisk": str(original), "replacementDisk": str(disks["files"]),
            "restoredBuilds": restored,
            "checks": ["remote-backup-job", "newest-snapshot", "retained-generations", "overlap-lock",
                       "missing-mount", "backup-provider-reboot", "unreadable-source-failure",
                       "checksum-mismatch", "truncated-archive", "empty-replacement-volume",
                       "original-server-offline", "metadata-restoration", "two-new-cpu-builds"]}
