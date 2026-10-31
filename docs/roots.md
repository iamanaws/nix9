# Shared root versions

[Network-root CPUs](netroot.md) select OS userland through the installation's
`roots`. Each built root has a separate `/systems/HASH-nix9-root-NAME` directory
on its CWFS provider. It contains OS files and public boot hooks. CPU stores,
homes, keys and other writable state stay in their machine directories.
An NDB auth-domain record points to the inventory's numeric auth-server address,
so fresh namespaces can authenticate before a system generation is selected.

## Build and publish

The default `roots.NAME.base` is `pkgs.netrootBase`: a normalized CPU userland
seed extracted from the pinned 9front 11952 VM. It includes native binaries,
startup scripts and namespace mount points. Building the seed on Linux requires
KVM; the native bootstrap includes it for later builds inside 9front.

`roots.NAME.files` adds or replaces public text files relative to the OS root.
Generated boot hooks and namespace includes are reserved. For example:

```nix
{
  roots.stable = { };
  roots.next.files."lib/site-version" = "2\n";
  machines.build.boot.root = "next";
  machines.batch.boot.root = "stable";
}
```

Each root contains hooks for the installation's network-root CPUs, so moving
one CPU does not rebuild another CPU's root. Changing a machine's state location
or boot hooks does create new root artifacts.

Build and retain the updated installation on the file server. With its `main`
filesystem mounted at `/n/site`:

```sh
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/netroot-next
installation=`{cat /usr/local/nix/state/gcroots/netroot-next}
root=`{cat $installation/roots/next}
rc $root/publish /n/site
boot=`{cat $installation/boot/build/path}
nix-store --export `{nix-store -qR $boot} > /n/site/machines/build/tmp/boot-next.export
echo $boot > /n/site/machines/build/tmp/boot-next.path
```

Publication copies into a `.partial` directory, then renames it into place.
Existing versions are never replaced. A failed copy leaves its partial directory
for inspection; remove it before retrying. Published directories have mode 0555.
Keep them unchanged while CPUs use them. An operator who owns them can still
change permissions through native filesystem tools.

To supply a different pinned seed, set `base` to a directory containing
`root.tar.gz` and `base.json`. The archive must contain a compatible amd64 CPU
userland and a `/lib/namespace` that includes `/lib/namespace.local`. Kernels
remain separately provisioned.

## Select one CPU

The CPU needs only its boot instructions. Full root bundles stay on the file
server. With native Nix active on that CPU, import and retain the instructions:

```sh
nix-store --import < /tmp/boot-next.export
nix-store --realise `{cat /tmp/boot-next.path} --add-root /usr/local/nix/state/gcroots/boot-next
boot=`{cat /usr/local/nix/state/gcroots/boot-next}
9fs 9fat
rc $boot/select /root /n/9fat
fshalt -r
```

`select` checks the published root, persistent identity and boot medium's
`nix9machine` before writing. It preserves kernel and hardware settings, saves
the previous `plan9.ini` as `plan9.bak`, and updates the generated boot settings.
It neither initializes state nor selects a Nix system generation. Other CPUs
continue using their configured roots. After reboot, `/cfg/nix9/root` identifies
the running root version.

Boot-setting writes on FAT are not power-loss atomic. Keep the saved settings
and console access available. An interrupted operation can leave `nix9lock`
on the medium; inspect the files before removing it and retrying.

## Roll back

Run the retained earlier boot artifact's `select` with the same mounts, then
reboot. If the CPU cannot boot, restore its saved settings from native recovery
media. Keep both published trees and compatible kernels available.

Root rollback reuses current writable state. Use `nix9-rebuild rollback`
separately for packages and module settings; neither operation restores user
data. Published trees remain until explicitly removed from CWFS. Nix GC manages
retained store artifacts, not these copies.
