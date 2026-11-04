# Network-root CPUs

A CPU can load its kernel from a small boot medium and mount its root from an
[authenticated CWFS server](storage.md). The medium needs the native loader,
compatible amd64 kernel, boot settings and private NVRAM credentials. It needs no
local OS filesystem. [PXE](netboot.md) can fetch the loader, kernel and settings
over the network. Authentication and file servers boot independently.

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
Installations with declared [shared homes](users.md) also append the provider's
`/usr` after the machine-specific tree.

## Prepare the file server

Follow the [installation walkthrough](install.md) to provision authentication,
CWFS and keys, publish a shared root and boot the CPUs. With the filesystem
mounted at `/n/site`, the root published and the installation in `$installation`,
the preparation interface is:

```sh
boot=`{cat $installation/boot/build/path}
rc $boot/prepare /n/site /tmp/bootstrap.tar $installation/systems/build
```

`prepare` seeds each machine's Nix files and initial Glenda home, initializes its
identity and refuses existing state. The optional system argument accepts a
store path or a file containing one. It must belong to this CPU. Preparation
stages that system and its boot closure under `/cfg/nix9/initial`; omitting the
argument prepares only the machine state for manual import and selection.
The root bundle already contains
`/cfg/nix9/boot/MACHINE-ID/{namespace,init}` and the common namespace include.
Additional native namespace rules can use `/cfg/HOST/namespace`.

## Boot and select

Merge `$boot/plan9.ini` into the boot medium's `plan9.ini`, preserving its kernel
and hardware settings. Provision the medium's NVRAM credentials with native
tools. Generated settings use numeric server addresses and the CPU's static
network configuration, so root mounting does not depend on Nix or DNS.

Start authentication and storage before the CPU. At its first console:

```sh
rc /cfg/nix9/initial/finish
fshalt -r
```

The finish command imports the staged closure, retains the initial boot artifact
at `system-initial-boot` beside the machine's system root, and checks and selects
the system. Correct any reported prerequisite and retry. After success it removes
the archive and records completion; later invocations do not select an old system.
Full root bundles stay on the file server.

After reboot, the selected system starts CPU access. Ordinary
[deployment](deployment.md), builds, generation selection and rollback work.
An unavailable root provider prevents boot; invalid credentials or missing or
mismatched machine state cannot start Nix.

See [root upgrades](roots.md) to publish another userland version, change one
CPU's next boot and return to an earlier root. Nix system generations select
packages and module settings separately. Local boot media and NVRAM credentials
remain native provisioning; [PXE](netboot.md) can manage kernel delivery.
