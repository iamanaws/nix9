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

With the current bootstrap or a release containing `nix9-rebuild` active:

```rc
nix9-rebuild switch configuration.nix
. /usr/local/pkg/nix9/system
fortune
cat /cfg/nix9/files/motd
```

## Generations

| Command | Effect |
| --- | --- |
| `nix9-rebuild build [CONFIGURATION]` | Build and retain at `state/gcroots/system-build`, without selecting. |
| `nix9-rebuild switch [CONFIGURATION]` | Build, check activation in a private namespace, then select. |
| `nix9-rebuild list` | List retained system generations. |
| `nix9-rebuild rollback` | Select the preceding generation. |
| `nix9-rebuild delete NUMBER` | Release an inactive generation for GC. |

The default configuration is `./configuration.nix`. The selected root is
`/usr/local/nix/state/gcroots/system`; boot retains its generation at
`system-boot` in the same directory. Selected and booted generations cannot
be deleted. Reboot into the selection before deleting an older booted generation.
Refresh sessions before deleting generations they use; runtime roots are not
discovered automatically.

Switching and rollback apply settings at different times:

| Setting | When it applies |
| --- | --- |
| Hostname | Immediately on selection, and at boot. |
| Packages, generated files, certificate pins and managed webfs | Boot, new login, or session refresh. |
| Ethernet, clock synchronization and CPU TCP scripts | Next boot. Running services and connections retain the booted generation. |
| Log files and permissions | Selection and boot. Login and refresh leave them alone. |

Refresh the current shell with `. /usr/local/pkg/nix9/system` after switching
or rolling back. Other sessions keep their namespaces until refreshed.
System selection is separate from [updating Nix itself](native.md#complete-releases).

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
The current bootstrap also activates retained generations that predate CPU hooks.

CPU console and rescue shells may have a separate namespace from startup
services. Source `/usr/local/pkg/nix9/system` there. New login shells activate
the selected system automatically.

System changes use the kernel service lock `#s/nix9-system`. An interrupted
command may leave it behind; remove it only after confirming no rebuild is running.
