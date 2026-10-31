# Network-root CPUs

A CPU can load its kernel from a small boot medium and mount its root from an
[authenticated CWFS server](storage.md). The medium needs the native loader,
compatible amd64 kernel, boot settings and private NVRAM credentials. It needs no
local OS filesystem. Authentication and file servers boot independently.

The [example](../examples/netroot/configuration.nix) describes auth, files and a
build CPU. On an existing inventory CPU, enable network-root boot with:

```nix
{
  boot.provider = "files";
}
```

The CPU must enable `services.cpu` and use a static primary interface matching
its inventory IP. The provider must enable CWFS on port 564. `defaults.auth`
identifies an independently booted authentication server. Evaluation rejects
boot dependencies that would require these servers to boot from another node.

| Setting | Default |
| --- | --- |
| `boot.provider` | Required CWFS provider inventory key. |
| `boot.rootDirectory` | `/systems/9front`, within the provider's `main` filesystem. |
| `boot.stateDirectory` | `/machines/MACHINE-ID`, within that filesystem. |

CPUs may share `rootDirectory`. Their state directories must be separate from
each other and from OS root trees. The generated namespace gives each CPU its
own canonical `/usr/local/nix`, package anchors, startup hooks, runtime key
files, native service directory, logs and temporary directory. Only that CPU
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
`/machines` parents for the operator. The example's root
prototype copies CPU userland from the server's existing 9front filesystem:

```sh
mount -c /srv/cwfs-nix9 /n/site main
mkdir -p /n/site/systems/9front
disk/mkfs -d /n/site/systems/9front -s /root $nix9/packages/examples/netroot/root.proto
```

The shared tree contains OS files. Machine keys belong in the per-CPU tree.
Keep a bootstrap archive available, for example `/tmp/bootstrap.tar` from the
[quick start](../README.md#quick-start). Prepare the CPU once:

```sh
boot=$installation/boot/build
rc $boot/prepare /n/site /tmp/bootstrap.tar
cp /adm/build.keys /n/site/machines/build/adm/cpu.keys
chmod 600 /n/site/machines/build/adm/cpu.keys
```

`prepare` seeds each machine's Nix files, initializes its identity and installs
`/cfg/nix9/boot/MACHINE-ID/{namespace,init}` in the shared root. A common include
in `/lib/namespace.local` restores the machine's bindings after hostname changes.
It refuses existing machine state or boot files and leaves formatting and
credentials to native provisioning. Additional native namespace rules can use
`/cfg/HOST/namespace`.

Stage the initial system closure for the first console boot:

```sh
system=`{cat $installation/systems/build}
nix-store --export `{nix-store -qR $system} > /n/site/machines/build/tmp/system.export
echo $system > /n/site/machines/build/tmp/system-path
```

## Boot and select

Merge `$boot/plan9.ini` into the boot medium's `plan9.ini`, preserving its kernel
and hardware settings. Provision the medium's NVRAM credentials with native
tools. Generated settings use numeric server addresses and the CPU's static
network configuration, so root mounting does not depend on Nix or DNS.

Start authentication and storage before the CPU. At its first console:

```sh
. /usr/local/pkg/nix9/activate
nix-store --import < /tmp/system.export
nix9-rebuild select `{cat /tmp/system-path}
fshalt -r
```

After reboot, the selected system starts CPU access. Ordinary
[deployment](deployment.md), builds, generation selection and rollback work.
An unavailable root provider prevents boot; invalid credentials or missing or
mismatched machine state cannot start Nix.

Nix system rollback selects packages and module settings. The provisioned kernel
and shared OS tree have their own lifecycle. Replacing a root tree requires its
per-machine boot files and compatible native userland. This first implementation
uses a boot medium; PXE and kernel construction remain native provisioning.
