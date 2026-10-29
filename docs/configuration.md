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

```rc
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

## Generations

| Command | Effect |
| --- | --- |
| `nix9-rebuild init MACHINE` | Set this machine's stable identity. Required before managing system generations. |
| `nix9-rebuild build [CONFIGURATION]` | Build and retain at `system-build` beside this machine's selected root. |
| `nix9-rebuild switch [CONFIGURATION]` | Build, check activation in a private namespace, then select. |
| `nix9-rebuild list` | List retained system generations. |
| `nix9-rebuild rollback` | Select the preceding generation. |
| `nix9-rebuild delete NUMBER` | Release an inactive generation for GC. |

The default configuration is `./configuration.nix`. The selected root is
`/usr/local/nix/state/gcroots/machines/MACHINE/system`; boot retains its generation at
`system-boot` in the same directory. Selected and booted generations cannot
be deleted. Reboot into the selection before deleting an older booted generation.
Refresh sessions before deleting generations they use; runtime roots are not
discovered automatically.

Switching and rollback apply settings at different times:

| Setting | When it applies |
| --- | --- |
| Hostname | Immediately on selection, and at boot. |
| Packages, generated files, certificate pins and managed webfs | Boot, new login, or session refresh. |
| NDB files and tools | Boot, new login, or session refresh. Running cs and DNS change at boot. |
| Ethernet, clock synchronization and CPU TCP scripts | Next boot. Running services and connections retain the booted generation. |
| Log files and permissions | Selection and boot. Login and refresh leave them alone. |

Refresh the current shell with `. /usr/local/pkg/nix9/system` after switching
or rolling back. Other sessions keep their namespaces until refreshed.
System selection is separate from [updating Nix itself](native.md#complete-releases).

## Machine identity

Initialize once before the first system selection. `init` is repeatable for the
same ID and rejects a different ID. Hostname changes leave this identity intact.
Plain Nix builds and package environments do not require a machine identity.

Set `machineId = "cpu1";` in a configuration to reject selection on another
machine. Configurations without this guard can be selected on any initialized machine.

For shared roots, keep writable Nix data on a machine-local filesystem. Set
`nix9local` to a kernel service name whose root contains `store`, `state` and
`log`. Native startup must post that service before Nix activation. The loader
mounts it before selecting Nix itself and restores those bindings after `newns`.
The optional boot setting `nix9machine` must agree with the saved local identity.
Do not change the backing store while clients are running.

For example, a machine booting from a local filesystem can post its original
Nix directory before binding shared files over `/usr/local/nix`:

```rc
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

[Services](services.md) documents networking, timesync, logging, webfs and TCP
scripts. These settings are optional.

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
