# Deploy an installation

`nix9-deploy` runs on a machine with native Nix active. It prepares and selects
systems from a built [installation](installation.md), using authenticated `rcpu`
connections to CPU servers and local commands for the caller's own machine.
Destinations need Nix, their stable machine identity, accounts and keys already
provisioned. Remote login must have permission to import closures and select
generations. It must also be able to activate its session's required shares.

## Build and apply

Build the inventory once and keep its output rooted:

```sh
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/installation
installation=`{cat /usr/local/nix/state/gcroots/installation}
nix9-deploy status $installation files cpu
nix9-deploy prepare $installation files cpu
nix9-deploy select $installation cpu files
```

Machine arguments are inventory keys. Omitting them requests every machine,
except `select-root`, which requests only network-root CPUs.
Matching the caller's stable identity chooses local execution. Other machines
require a running CPU service. Run terminal deployment locally after
[importing the bundle's closure](transport.md#binary-caches). Destinations do
not evaluate the inventory or build packages.

`prepare` exports only store objects absent from each destination, imports them,
retains the intended system and runs `nix9-rebuild check`. It preserves selected
generations. Retry the same command after a failed transfer; complete imported
objects are reused, and unfinished objects are transferred again.

`select` first checks every requested machine. For a scheduler, it also checks
that its remote job targets have prepared their intended systems. This keeps
the new commands available before enabling their schedules. It then selects
machines in the order given. Repeating selection reuses existing generations.
Session mounts may be cyclic, so they do not determine a deployment order.
Select job targets before their schedulers when commands need changed target
settings or session mounts. Preparation retains commands; selection makes the
target's new configuration available to subsequent sessions.

Reboot machines explicitly when ready. Session refresh and service activation
follow the ordinary [generation rules](configuration.md#generations).

## Shared OS roots

For provisioned [network-root CPUs](netroot.md), `prepare` first publishes each
required root once on its CWFS provider. The provider must be the coordinator
or offer administrative CPU access. It needs a running managed CWFS service and
a writable `/systems` directory. Complete published versions are reused;
failed copies leave a `.partial` directory to inspect and remove before retrying.

CPUs receive their system closures and small boot artifacts. Full root bundles
stay on the provider. Preparation checks the published boot hooks and persistent
machine identity, without initializing state or changing boot settings.

Select the next OS root explicitly:

```sh
nix9-deploy prepare $installation build batch
nix9-deploy select-root $installation build
nix9-deploy status $installation build batch
```

`select-root` checks every requested CPU's prepared artifact, intended provider,
published hooks, persistent identity and boot medium before changing any boot
settings. It then selects machines in argument order. Repeating an unchanged
selection preserves `plan9.bak`. Reboot each CPU explicitly when ready.
Ordinary `select` still selects packages and module settings separately.

`machines.NAME.deployment.bootMedium` defaults to `/n/9fat`. When needed, deployment
mounts the CPU's single local `9fat` partition through the native FAT server.
The server uses its own namespace and shares its cache with console mounts.
Deployment rejects ambiguous local disks and avoids devices exported by the
coordinator. A custom path must already be mounted in the administration
session's namespace. Boot media and kernels remain provisioned
through native tools. See [root recovery](roots.md#roll-back) for FAT write limits.

## Connections

The connection defaults to the inventory IP and caller's native user. For a
different administration address or identity:

```nix
{
  machines.cpu.deployment = {
    host = "cpu-admin";
    user = "glenda";
    keyPattern = "dom=lab user=glenda";
    timeout = 300;
  };
}
```

`host` and `user` default to `null`. The default key pattern selects
`defaults.authdom` when set. `timeout` limits each whole remote operation,
including transfer, to 300 seconds by default. With CPU access enabled, a declared
user must be in its allowed users. Client keys come from the caller's factotum.
An explicit `host` also permits connecting when the intended configuration
disables CPU access; the currently running listener remains available until reboot.

## Status and recovery

`status` shows prepared, selected and booted systems alongside the bundle's
intended system. Network-root CPUs also show `root-intended`, `root-prepared`
boot artifacts, `root-running`, `root-next`, and the running and next providers' addresses.
`-` means no recorded path. `root-reboot` compares running and next-boot roots;
`reboot required` covers pending system or root changes. These fields do not test
service health or mean the machine matches the bundle's intended configuration.

A failed initial check prevents selection on all requested machines. A failure
during selection can leave earlier machines updated. Query status, resolve the
failure, then repeat the affected operation. Use `nix9-rebuild rollback` for a
system generation. For an OS root, run `prepare` and `select-root` with the
retained earlier installation, then reboot.

Each destination retains one prepared closure per installation and machine at
`/usr/local/nix/state/gcroots/deployments/INSTALLATION/MACHINE-ID`. A later
preparation replaces that root. Remove it manually when abandoning a deployment;
selected and historical generations have their own roots. A CPU's prepared boot
artifact uses the same path with `-boot` appended. Providers retain root bundles
under `MACHINE-ID-roots/VERSION`; these and their published CWFS copies require
explicit removal when no longer needed. Abrupt termination
can leave `#s/nix9-deploy-*` locks or coordinator temporary files under
`/usr/local/nix/state/deploy-*`. Remove them only after checking that the
deployment has stopped.
