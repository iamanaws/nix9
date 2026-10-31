# Deploy an installation

`nix9 deploy` builds an [installation](installation.md), prepares its closures
and selects the requested machines. It uses authenticated `rcpu` connections to
CPU servers and local commands for the caller's own machine. Destinations need
Nix, stable machine identities, accounts and keys already provisioned. Remote
login must have permission to import closures, select generations and activate
its required session mounts.

## Common workflow

From the directory containing the inventory's `default.nix`:

```sh
nix9 deploy cpu files
nix9 status cpu files
```

Deployment prepares the closures and shared roots, checks every requested machine,
then selects in argument order. Select job targets before their schedulers when
commands need changed target settings or session mounts. Session mounts can be
cyclic and do not define a deployment order.

Use `--all` instead of machine names to request the whole inventory. `--file FILE`
chooses another source expression. Mutating operations require names or `--all`.
Matching the caller's stable identity chooses local execution; other machines
require a running CPU service. Terminals without CPU access deploy locally.
Destinations import built closures without evaluating configurations.

The last successful build of each source expression is retained under
`/usr/local/nix/state/gcroots/installations/`. The reference is keyed by the
canonical source path, so edits keep the same reference. Deployment prints its
location. A failed build preserves the preceding bundle.

`show`, remote `status` and `deploy --select` reuse that reference without building
or evaluating the source. `nix9 status` without arguments inspects the local machine.
`show` describes NDB, service endpoints, exports, mounts, bindings, builders, jobs
and shared-root boot settings offline. It does not test service health.

## Prepare and select separately

```sh
nix9 deploy --prepare cpu files
nix9 show
nix9 deploy --select cpu files
```

`--prepare` builds and transfers only missing store objects, retains the intended
systems and runs their checks. Required job targets are prepared too, including
their dependencies; their selections stay unchanged unless requested. Shared roots
are published before CPU preparation. Retry after a failed transfer: complete
imported objects are reused.

`--select` checks all requested machines and their prepared job targets before
selecting any machine. Repeating selection reuses existing generations.
`--prepare` and `--select` are mutually exclusive.

For a separately built, imported or retained bundle, use `--from`:

```sh
bundle=/usr/local/nix/state/gcroots/reviewed-installation
nix-build default.nix -A build --out-link $bundle
nix9 show --from $bundle
nix9 deploy --prepare --from $bundle cpu files
nix9 deploy --select --from $bundle cpu files
```

`--from` accepts a bundle store path or a file containing one. It skips building
and source-reference lookup. It is mutually exclusive with `--file`. Plain
`deploy --from BUNDLE` combines preparation and selection of that exact bundle.

Reboot explicitly when ready. Session refresh and service activation follow the
ordinary [generation rules](configuration.md#generations). See `nix9 help` for
command syntax and `nix9-rebuild help` for local builds and generation management.

## Shared OS roots

For provisioned [network-root CPUs](netroot.md), preparation publishes each
required root once on its CWFS provider. The provider must be the coordinator
or offer administrative CPU access. It needs a running managed CWFS service and
a writable `/systems` directory. Complete published versions are reused;
failed copies leave a `.partial` directory to inspect and remove before retrying.

CPUs receive their system closures and small boot artifacts. Full root bundles
stay on the provider. Preparation checks the published boot hooks and persistent
machine identity, without initializing state or changing boot settings.

Select the next OS root explicitly:

```sh
nix9 deploy --prepare build batch
nix9 select-root build
nix9 status build batch
```

`select-root` checks every requested CPU's prepared artifact, intended provider,
published hooks, persistent identity and boot medium before changing any boot
settings. It then selects machines in argument order. `--all` requests every
network-root CPU. Repeating an unchanged selection preserves `plan9.bak`.
Reboot each CPU explicitly when ready. Ordinary deployment selects packages
and module settings separately from OS roots.

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
system generation. For an OS root, use `deploy --prepare` and `select-root`
with `--from` pointing at the retained earlier installation, then reboot.

Each destination retains one prepared closure per installation and machine at
`/usr/local/nix/state/gcroots/deployments/INSTALLATION/MACHINE-ID`. A later
preparation replaces that root. Remove it manually when abandoning a deployment;
selected and historical generations have their own roots. A CPU's prepared boot
artifact uses the same path with `-boot` appended. Providers retain root bundles
under `MACHINE-ID-roots/VERSION`; these and their published CWFS copies require
explicit removal when no longer needed. Remove the coordinator reference when
abandoning a source. Abrupt termination can leave `#s/nix9-deploy-*` locks or
coordinator temporary files under
`/usr/local/nix/state/deploy-*`. Remove them only after checking that the
deployment has stopped.
