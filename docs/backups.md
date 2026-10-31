# Backups and replacement storage

`services.backups` archives directories from the newest completed CWFS dump onto
an independent machine. Each run writes a full native Plan 9 archive, a SHA-256
checksum and a source record. Transfer to the backup server uses an authenticated
TLS directory export.

## Configure a backup

On a machine with [session mounts](sharing.md#mount-in-a-session):

```nix
{
  services.backups.projects = {
    sourceMount = "history";
    destinationMount = "archives";
    paths = [ "projects" ];
  };
}
```

`sourceMount` must name a native TCP mount with `attach = "dump"`.
`destinationMount` must name a writable TLS directory export on separate storage.
Set its provider's `readOnly = false`. `paths`
lists directories relative to the snapshot root. Paths cannot overlap or contain
traversal. The runner checks that both managed mounts are still present.

With the system active, run manually:

```sh
rc $nix9System/services/backups/projects/run
```

Or use an ordinary [installation job](jobs.md):

```nix
{
  jobs.projects-backup = {
    scheduler = "auth";
    target = "build";
    user = "glenda";
    schedule = "0 6 * * *";
    command = "exec rc $nix9System/services/backups/projects/run";
  };
}
```

The job uses the target's selected backup configuration and session mounts. Its
normal job log records the selected snapshot, completion path and failures.
Schedule it after the [CWFS dump](storage.md#restore-a-file). A run archives the
newest existing dump and does not request a new one.

## Six-machine example

The [backup example](../examples/backup/configuration.nix) extends the storage
installation with a backup server at `10.0.2.105`. Copy both example directories
to preserve its relative import:

```sh
mkdir /usr/glenda/backup-lab
cp -r $nix9/packages/examples/storage $nix9/packages/examples/backup /usr/glenda/backup-lab/
cd /usr/glenda/backup-lab/backup
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/backup-lab
```

Provision the storage installation's accounts and keys, plus the `backup` server
identity. `/adm/backup.keys` contains its server key; the auth machine's
`/adm/scheduler.keys` contains Glenda's client key. Keep these runtime files
private. The build CPU already has delegation for Glenda. Native provisioning
must place `/usr/glenda/archives` on independent persistent storage.

The build CPU mounts history and archives optionally, so their absence does not
prevent ordinary CPU login. A backup still requires both. Select the target
before the scheduler using the [deployment workflow](deployment.md).

## Recover onto a replacement file server

Provision a replacement with an empty CWFS volume, filesystem accounts, the file
server's authentication key and its selected Nix system. Configure its address
and identity to replace the lost server. Provision `/projects` for the workspace
bindings, then establish a fresh terminal session against the replacement.

The terminal in the example includes `pkgs.diskArchive` and mounts the backup
export. Inspect the completed generations and select one explicitly:

```sh
ls -d /n/archives/projects/[0-9]*
disk/restore /n/archives/projects/001793376000-123 /n/work
rcpu -h build -c 'nix-build /usr/glenda/work'
rcpu -h batch -c 'nix-build /usr/glenda/work'
```

Use an actual generation name from the listing. `disk/restore` verifies the
checksum and reads the entire archive before extracting. It restores ownership,
permissions and file modification times through native filesystem permissions.
Use a fresh destination; extraction merges files into an existing tree.
The original file server and its dump device are unnecessary for recovery.

Completed generations are directories named `EPOCH-PID` under `DESTINATION/NAME`.
Runs publish them by renaming `.partial-EPOCH-PID` only after successful archive
creation and readback. A `lock` directory records the worker and excludes
overlapping runs. Failed runs leave partial data for inspection; a crash can
also leave the lock. Remove these
only after checking that no backup is active.

Archives remain until removed manually. They use full-copy space, without
deduplication or automatic pruning. The writer can modify its backup directory.
This workflow covers declared data trees; authentication databases, keys, boot
configuration and Nix machine state need separate recovery copies.
