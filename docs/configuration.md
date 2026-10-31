# System configuration

The native package set provides `mkSystem`. Save
[the example](../examples/system/configuration.nix) as `configuration.nix`
in the guest, or start with:

```nix
let
  pkgs = import <nix9>;
in
pkgs.mkSystem {
  hostName = "nix9";
  networking.enable = true;
  services.webfs.enable = true;
  packages = [ pkgs.fortune ];
  files."motd" = "Welcome to nix9.\n";
}
```

With Nix active:

```sh
nix9-rebuild init cpu1
nix9-rebuild switch configuration.nix
. /usr/local/pkg/nix9/system
fortune
cat /cfg/nix9/files/motd
```

Configurations can use `imports = [ ./common.nix ];` and module functions
receiving `lib`, `pkgs` and `config`. The bundled `pkgs.lib` provides standard
option types, `mkDefault`, `mkForce`, `mkIf` and list ordering without guest
flakes or network access.

Use [an installation inventory](installation.md) to describe several machines,
generate their discovery records and connect session mounts to declared exports.
It can also select [remote Nix builders](builders.md) by CPU machine name.

## Generations

| Command | Effect |
| --- | --- |
| `nix9-rebuild init MACHINE` | Set this machine's stable identity. Required before managing system generations. |
| `nix9-rebuild build [CONFIGURATION]` | Build and retain at `system-build` beside this machine's selected root. |
| `nix9-rebuild switch [CONFIGURATION]` | Build, check activation in a private namespace, then select. |
| `nix9-rebuild check PATH` | Verify a local system closure and run selection preflight without selecting it. |
| `nix9-rebuild select PATH` | Check and select a local system closure without evaluating a configuration. |
| `nix9-rebuild list` | List retained system generations. |
| `nix9-rebuild rollback` | Select the preceding generation. |
| `nix9-rebuild delete NUMBER` | Release an inactive generation for GC. |

The default configuration is `./configuration.nix`. The selected root is
`/usr/local/nix/state/gcroots/machines/MACHINE/system`; boot retains its generation at
`system-boot` in the same directory. Selected and booted generations cannot
be deleted. Reboot into the selection before deleting an older booted generation.
Refresh sessions before deleting generations they use; runtime roots are not
discovered automatically.

`check` and `select` require a complete, registered system at a canonical
`/usr/local/nix/store/...` output path. [Import or realise its closure](transport.md#binary-caches)
first. These commands do not evaluate configurations, build outputs or fetch
missing paths. Selection checks the contents of the system and every dependency.

Both commands check the machine identity guard, activation, service settings,
runtime prerequisites and startup hooks. `check` leaves the selected generation,
history, hostname, hooks and logs unchanged. Activation preflight can create
missing mount points and an empty revocation file. A temporary GC root protects
the candidate during checking and selection; retain imported outputs separately
if they must survive GC before selection.

Selection and rollback apply settings at different times:

| Setting | When it applies |
| --- | --- |
| Hostname | Immediately on selection, and at boot. |
| Packages, generated files, certificate pins and managed webfs | Boot, new login, or session refresh. |
| Nix builders and build settings | Next Nix invocation after login or session refresh. |
| Rio, Acme and plumbing settings | Next `nix9-session` invocation. |
| NDB files and tools | Boot, new login, or session refresh. Running cs and DNS change at boot. |
| Shared-file mounts and directory bindings | New login or session refresh, in that session's namespace. |
| Ethernet and clock synchronization | Next boot. |
| CPU TCP scripts, CPU access, file exports and authentication policy | Next CPU-server boot. Running services and connections retain the booted generation. |
| CWFS data service and daily dump policy | Next CPU-server boot. Project contents and historical dumps persist across system selections. |
| Backup definitions | Next invocation in an activated system session. See [backups](backups.md). |
| Log files and permissions | Selection and boot. Login and refresh leave them alone. |
| Scheduled jobs | Enabling and key loading require CPU-server reboot. A running scheduler reloads the selected schedules within a minute; running jobs continue. |
| Persistent directories and their metadata | Selection, rollback and boot. Login and refresh leave them alone. |

Refresh the current shell with `. /usr/local/pkg/nix9/system` after selection
or rollback. Other sessions keep their namespaces until refreshed.
System selection is separate from [updating Nix itself](native.md#complete-releases).

## Machine identity

Initialize once before the first system selection. `init` is repeatable for the
same ID and rejects a different ID. Hostname changes leave this identity intact.
Plain Nix builds and package environments do not require a machine identity.

Set `machineId = "cpu1";` in a configuration to reject selection on another
machine. Configurations without this guard can be selected on any initialized machine.

For shared roots, give each machine its own writable Nix data. The
[network-root inventory](netroot.md) prepares separate persistent directories on
CWFS. For a manually composed namespace, set
`nix9local` to a kernel service name whose root contains `store`, `state` and
`log`. Native startup must post that service before Nix activation. The loader
mounts it before selecting Nix itself and restores those bindings after `newns`.
The optional boot setting `nix9machine` must agree with the saved local identity.
Do not change the backing store while clients are running.

For example, a machine booting from a local filesystem can post its original
Nix directory before binding shared files over `/usr/local/nix`:

```sh
srvfs local-nix /root/usr/local/nix
```

Set the boot variables in `plan9.ini` so later logins inherit them:

```ini
nix9local=local-nix
nix9machine=cpu1
```

Post the service in native startup before the Nix hook. Disk and network-root
boot provisioning remain separate from `mkSystem`.

## Machine settings

`hostName` is a lowercase DNS label of at most 63 characters.
`packages` uses the same command-collision checks and dependency retention as
[buildEnv](native.md#environments).

`files` maps relative paths to text under `/cfg/nix9/files`. Paths cannot escape
that directory or overlap a parent file. Removing a declaration removes it from
the managed view. Store references in the text retain their dependencies through
GC. Native machine files such as `/cfg/nix9/termrc` remain visible.

`webfs.certificatePins` maps lowercase DNS hosts or IPv4 addresses to nonempty
lists of 64-digit SHA-256 hex fingerprints. Pins override the same host's manual
file in the activated namespace. Removing a host reveals its manual policy;
other hosts and the shared revocation file remain intact. Activation creates an
empty revocation file only if none exists. See [HTTPS trust](transport.md#https-trust)
for the policy format and revocation behavior. A manual webfs must be restarted
to use changed pins; [managed webfs](services.md#webfs) handles this on refresh.

[Services](services.md) documents networking, timesync, logging, webfs, TCP
scripts, authenticated access and [shared files](sharing.md). These settings are
optional.

Use [session bindings](namespaces.md) to compose local directories, package
outputs and shares into ordered filesystem views.
For Rio, Acme and plumbing startup, see [graphical sessions](workstation.md).

## Persistent directories

Declare directories outside the store:

```nix
directories."/usr/glenda/projects" = {
  mode = "0750";
  owner = "glenda";
  group = "glenda";
};
```

`mode` defaults to `0755`. `owner` and `group` default to `null`, preserving
existing ownership. New directories use their creator and inherit their parent's
group. Missing parents use `0755` unless declared separately.

Selection and boot prepare directories before managed services use them.
Rollback reapplies the preceding declaration. Contents and child permissions
stay intact; removing a declaration leaves its directory and data in place.

`check` inspects paths and conflicts without creating directories or changing
metadata. The file server decides whether creation and metadata changes are
permitted when applied. Owners and groups must already exist there. Changing an
owner normally requires native file-server provisioning permission.
Preparation errors prevent selection or managed startup. Directories already
created or changed remain in place if a later step fails.

Paths must be canonical absolute strings without store references. Declarations
cannot cover native namespace paths, the Nix runtime, generated system mounts or
configured session mounts. Preparation also rejects paths inside a managed share
retained by the current session. Existing files and directories with special
mode flags are rejected.

## Boot integration

The first switch wraps `/rc/bin/termrc.local`, `/rc/bin/cpurc.local` and
`/rc/lib/rcmain.local`. Existing scripts move to `.nix9-original` backups and
run before the managed hook. Later switches reject edited or removed wrappers
and missing backups.

CPU support requires an already configured CPU server with `service=cpu` and
CPU init. Nix9 preserves native `/cfg/$sysname/cpurc`, `cpustart`, authentication
and unmanaged services. It does not edit `plan9.ini`.

CPU console and rescue shells may have a separate namespace from startup
services. Source `/usr/local/pkg/nix9/system` there. New login shells activate
the selected system automatically.

System changes use `#s/nix9-system-MACHINE`; initialization uses `#s/nix9-machine`.
An interrupted command may leave a lock behind; remove it only after confirming
no rebuild is running.
