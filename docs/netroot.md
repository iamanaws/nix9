# Network-root CPUs

A CPU can load its kernel from a small boot medium and mount its root from an
[authenticated CWFS server](storage.md). The medium needs the native loader,
compatible amd64 kernel, boot settings and private NVRAM credentials. It needs no
local OS filesystem. Authentication and file servers boot independently.

The [example](../examples/netroot/configuration.nix) describes auth, files and a
build CPU. Declare a root and assign it to a CPU in the installation:

```nix
{
  roots.stable = { };
  machines.build.boot = {
    provider = "files";
    root = "stable";
  };
}
```

The CPU must enable `services.cpu` and use a static primary interface matching
its inventory IP. The provider must enable CWFS on port 564. `defaults.auth`
identifies an independently booted authentication server; `defaults.authdom`
must match the runtime keys' domain. Evaluation rejects
boot dependencies that would require these servers to boot from another node.
Network-root machine IDs are limited to 27 characters by native namespace expansion.

| Setting | Default |
| --- | --- |
| `boot.provider` | Required CWFS provider inventory key. |
| `boot.root` | Required name in the installation's `roots`. |
| `boot.stateDirectory` | `/machines/MACHINE-ID`, within that filesystem. |

CPUs may share a root version. Their state directories must be separate from
each other and from OS root trees. The generated namespace gives each CPU its
own `/usr`, canonical `/usr/local/nix`, package anchors, startup hooks, runtime key
files, Nix configuration mount points, TLS revocations, native service directory,
logs and temporary directory. Only that CPU
opens its Nix database.
Native `newns` and remote CPU login recreate these bindings.

## Prepare the file server

Provision CWFS, filesystem accounts and authentication as described in
[storage](storage.md) and [access](access.md). The example needs `files`, `build`
and `glenda` in the auth database and `glenda` in the filesystem's user table.
The CPU's NVRAM root-login key uses `glenda` in `nix9.netroot`; its separate
CPU-service key belongs to `build`.

On the file server with native Nix, copy the example's `.nix` files into a
writable directory and adjust addresses and devices for the site:

```sh
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/netroot
installation=`{cat /usr/local/nix/state/gcroots/netroot}
```

Mount `main` with an authorized client key. Provision writable `/systems` and
`/machines` parents for the operator, then publish the built root:

```sh
mount -c /srv/cwfs-nix9 /n/site main
root=`{cat $installation/roots/stable}
rc $root/publish /n/site
```

The shared tree contains OS files. Machine keys belong in the per-CPU tree.
Keep a bootstrap archive available, for example `/tmp/bootstrap.tar` from the
[quick start](../README.md#quick-start). Prepare the CPU once:

```sh
boot=`{cat $installation/boot/build/path}
rc $boot/prepare /n/site /tmp/bootstrap.tar
cp /adm/build.keys /n/site/machines/build/adm/cpu.keys
chmod 600 /n/site/machines/build/adm/cpu.keys
```

`prepare` seeds each machine's Nix files and initial Glenda home, initializes its
identity and refuses existing state. The root bundle already contains
`/cfg/nix9/boot/MACHINE-ID/{namespace,init}` and the common namespace include.
Additional native namespace rules can use `/cfg/HOST/namespace`.

Stage the CPU's system and boot instructions. Full root bundles stay on the
file server:

```sh
system=`{cat $installation/systems/build}
nix-store --export `{nix-store -qR $system $boot} > /n/site/machines/build/tmp/initial.export
echo $system > /n/site/machines/build/tmp/system-path
echo $boot > /n/site/machines/build/tmp/boot-path
```

## Boot and select

Merge `$boot/plan9.ini` into the boot medium's `plan9.ini`, preserving its kernel
and hardware settings. Provision the medium's NVRAM credentials with native
tools. Generated settings use numeric server addresses and the CPU's static
network configuration, so root mounting does not depend on Nix or DNS.

Start authentication and storage before the CPU. At its first console:

```sh
. /usr/local/pkg/nix9/activate
nix-store --import < /tmp/initial.export
nix-store --realise `{cat /tmp/boot-path} --add-root /usr/local/nix/state/gcroots/boot-stable
nix9-rebuild select `{cat /tmp/system-path}
fshalt -r
```

After reboot, the selected system starts CPU access. Ordinary
[deployment](deployment.md), builds, generation selection and rollback work.
An unavailable root provider prevents boot; invalid credentials or missing or
mismatched machine state cannot start Nix.

See [root upgrades](roots.md) to publish another userland version, change one
CPU's next boot and return to an earlier root. Nix system generations select
packages and module settings separately. Kernels, boot media, NVRAM credentials
and PXE remain native provisioning.
