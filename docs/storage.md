# Storage and recovery

`services.cwfs` starts a separate CWFS64x data filesystem on a provisioned CPU
server. It manages startup, authentication keys and daily dump policy. Native
tools provision devices and filesystem accounts. Selection never formats,
reams or recovers a disk.

CWFS provides writable `main` and read-only `dump` trees. The module uses the
pinned 9front implementation. GEFS was considered for its retention controls,
but its manual still labels it experimental. See the native
[CWFS](https://github.com/9front/9front/blob/602faae9a52f342a40b086d10b23c71c82dd52d7/sys/man/4/cwfs)
and [configuration](https://github.com/9front/9front/blob/602faae9a52f342a40b086d10b23c71c82dd52d7/sys/man/8/fsconfig) manuals.

## Configure the data server

Inside `mkSystem`:

```nix
services.cwfs = {
  enable = true;
  configDevice = "/adm/storage/config";
  deviceMap = { w0 = "/adm/storage/cache"; w1 = "/adm/storage/worm"; };
  keyFile = "/adm/files.keys";
  autoDump = true;
  dumpHour = 5;
};
```

Devices may be files or native disk partitions. The configuration must already
contain a cached-worm `main` filesystem and its `dump` tree, for example:

```text
filsys main cw0fw1
filsys dump o
```

For the example, provision the filesystem's `glenda` account and a writable
`/projects` directory. Filesystem accounts are separate from authentication-server
accounts. On a freshly reamed volume, initialize the console's user table with
`users default` and create `/adm/users` before adding accounts. Keep
authentication enabled in the on-disk CWFS configuration.
Selection rejects unformatted configuration blocks, `noauth`, `readonly`,
missing devices and unsafe key-file permissions before changing generations.
The key file contains native factotum commands and stays outside Nix expressions
and the store. See [authentication](access.md).

`port` defaults to 564. `cachePercent` defaults to 10, with a range of 1 to 80.
The server posts `/srv/cwfs-nix9` and its owner-only administrative console
`/srv/cwfs-nix9.cmd`. Diagnostics go to `/sys/log/cwfs`. Native `fshalt`
discovers and halts the server before power-off or reboot.

The server needs CPU-mode boot and working networking. It can start before the
authentication server; clients need that server when establishing sessions.
Settings and dump policy take effect at CPU-server reboot. Selection and
rollback leave the running server and its data alone.

## Shared workspace

The bundled [example](../examples/storage/configuration.nix) separates auth,
storage, two CPU servers named `build` and `batch`, and a terminal. With native
Nix active:

```sh
cp -r $nix9/packages/examples/storage /usr/glenda/storage-lab
cd /usr/glenda/storage-lab
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/storage-lab
```

Set site addresses, provision the data volume and keys, then use the
[installation workflow](installation.md) to select systems. The sample uses
`10.0.2.100` through `10.0.2.104`; provide DHCP reservations or static networking.
Both CPU identities need delegation for `glenda`, as declared in the example.
Each CPU keeps its own writable Nix store.

Provision `files`, `build`, `batch` and `glenda` in the auth database. The file
server needs its server key in `/adm/files.keys`; each CPU's `/adm/cpu.keys`
contains its own server and delegation keys. The terminal needs Glenda's client
key. All use authentication domain `nix9.storage`.

Inventory mounts select a native filesystem attach:

```nix
machines.build.mounts.work = { provider = "files"; fileSystem = "main"; };
machines.terminal.mounts.history = {
  provider = "files";
  fileSystem = "dump";
  mountPoint = "/n/history";
};
```

These use authenticated native 9P over TCP. Filesystem data is unencrypted on
this connection. Directory exports retain their authenticated TLS transport.
Native filesystem permissions govern access to `main` and `dump`.

The example binds `/n/work/projects` at `/usr/glenda/work` in terminal and CPU
sessions. Edit a Nix project there, then build it on either CPU:

```sh
. /usr/local/pkg/nix9/system
rcpu -h build -c 'nix-build /usr/glenda/work'
rcpu -h batch -c 'nix-build /usr/glenda/work'
```

## Restore a file

With `autoDump` enabled, CWFS takes daily dumps at `dumpHour` in the server's
native timezone. A dump freezes a historical view; later writes go to the current
tree. To request one immediately on the file server:

```sh
echo dump >> /srv/cwfs-nix9.cmd
```

Browse dated directories under `/n/history/YYYY/MMDD`. Further dumps on the
same day have a numeric suffix. Use an existing date to restore a file:

```sh
cp /n/history/2026/1030/projects/hello.c /usr/glenda/work/hello.c
```

System rollback does not restore project contents. CWFS retains dump history on
its archival device; this module does not prune it. Watch available space through
native CWFS tools. Snapshots share the storage device and do not replace a
separate backup.

Provider reboots close active mounts. New CPU sessions reconnect to persistent
data and history. See [session mount behavior](sharing.md#changes-and-failures).
