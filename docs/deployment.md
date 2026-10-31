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

Machine arguments are inventory keys. Omitting them requests every machine.
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

`status` queries machines for their prepared, selected and booted paths alongside
the intended path in the bundle. `-` means no recorded path. `reboot required`
means selected and booted paths differ; it does not test service health. A
machine can be booted into its selected generation while differing from the
bundle's intended generation.

A failed initial check prevents selection on all requested machines. A failure
during selection can leave earlier machines updated. Query status, resolve the
failure, then repeat `prepare` or `select` for the affected machines. Use each
machine's `nix9-rebuild rollback` to restore an earlier generation.

Each destination retains one prepared closure per installation and machine at
`/usr/local/nix/state/gcroots/deployments/INSTALLATION/MACHINE-ID`. A later
preparation replaces that root. Remove it manually when abandoning a deployment;
selected and historical generations have their own roots. Abrupt termination
can leave `#s/nix9-deploy-*` locks or coordinator temporary files under
`/usr/local/nix/state/deploy-*`. Remove them only after checking that the
deployment has stopped.
