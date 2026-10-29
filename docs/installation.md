# Installation inventory

`pkgs.mkInstallation` describes machines together and produces their `mkSystem`
closures, shared NDB records and a manifest. Start with the bundled
[file/auth, CPU and terminal example](../examples/installation/configuration.nix).
Native boot, accounts and keys remain provisioning prerequisites. The example
declares its shared project directory. See [authentication](access.md) and
[sharing](sharing.md).

## Try the example

With native Nix active, copy the example into a writable directory:

```sh
cp -r $nix9/packages/examples/installation /usr/glenda/installation
cd /usr/glenda/installation
nix-instantiate --eval --strict --json default.nix -A manifest
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/installation
```

Edit `configuration.nix` for the site before selecting a system. The example
advertises `10.0.2.100` through `10.0.2.102` and enables DHCP. Configure DHCP
reservations or static networking to make those addresses reachable. Inventory
addresses describe discovery; native networking settings configure interfaces.

Select the appropriate system on each provisioned machine. On a CPU server
that built the bundle locally:

```sh
installation=`{cat /usr/local/nix/state/gcroots/installation}
system=`{cat $installation/systems/cpu}
nix9-rebuild init cpu
nix9-rebuild check $system
nix9-rebuild select $system
```

Selection and reboot follow the usual [system rules](configuration.md#generations).
Each machine keeps its own writable Nix store and database.

## Inventory and relationships

The builder accepts modules with `imports`, overrides and module functions, just
like `mkSystem`. Its main settings are:

| Setting | Meaning |
| --- | --- |
| `name` | Installation name, default `installation`. |
| `machines.NAME.ip` | Advertised IPv4 address. |
| `machines.NAME.machineId` | Stable provisioned identity, default `NAME`. |
| `machines.NAME.hostName` | Mutable hostname, default `NAME`. |
| `machines.NAME.configuration` | Ordinary `mkSystem` module declaring packages, services and machine settings. |
| `defaults.auth`, `defaults.fs`, `defaults.cpu` | Discovery providers, referenced by inventory key. Each defaults to `null`. |
| `defaults.authdom` | Public authentication domain, default `null`. |

Declare a session mount by provider and export:

```nix
machines.cpu.mounts.projects = {
  provider = "files";
  export = "projects";
};
```

`export` defaults to the mount's name. The builder derives its address from the
provider's hostname and export port. `mountPoint`, `required`, `timeout` and
`keyPattern` follow [session mount](sharing.md#mount-in-a-session) settings.
The default key pattern selects `defaults.authdom` when set.

The inventory owns identities, hostnames, NDB host records and these named
mounts. Configure NDB includes and DNS through each machine's `configuration`.
Use `configuration.namespace.mounts` for shares outside the inventory.

Evaluation checks every machine, even when requesting one system. It rejects
duplicate identities, hostnames or addresses, missing providers or exports,
providers without the referenced role, conflicting ports and invalid system
settings. Optional mounts still require a valid declaration; `required = false`
controls runtime availability.

## Outputs

| Output | Contents |
| --- | --- |
| `systems.NAME` | That machine's system derivation, guarded by its inventory identity. |
| `discovery` | Generated `services.ndb` host records and discovery defaults. |
| `manifest` | Versioned data containing identities, system paths, roles, endpoints, mounts and dependencies. |
| `build` | An output containing `manifest.json`, `ndb` and one closure-path file per machine under `systems/`. Keeping it rooted retains all system closures. |

Roles come from enabled authentication, CPU and export services. Manifest
dependencies describe authentication and named mounts needed by sessions.
Discovery defaults for CPU and file servers are locations, not boot dependencies.
Machines may mount each other's exports because their boot namespaces start
independently of user sessions.

The flake exposes the constructor as `lib.mkInstallation` for callers supplying
`lib`, `packages`, `mkDerivation` and `buildEnv`. The native package set binds
these arguments.

Build on one machine, then transfer closures through
[export/import or signed caches](transport.md#binary-caches). On the destination,
pass the imported system's store path to `nix9-rebuild check` and
`nix9-rebuild select`; the configuration expression is needed only on the builder.
Coordinated rollout, deployment health checks and rollback across machines require
manual orchestration.
