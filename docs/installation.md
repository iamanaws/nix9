# Installation inventory

`pkgs.mkInstallation` describes machines together and produces their `mkSystem`
closures, shared NDB records and a manifest. Start with the bundled
[file/auth, CPU and terminal example](../examples/installation/configuration.nix).
Native boot, accounts and keys remain provisioning prerequisites. The example
declares its shared project directory. See [authentication](access.md) and
[sharing](sharing.md).

A machine can provide several services. Enable them in its `configuration`;
the inventory derives its roles. `defaults` names providers for the shared NDB
address book. A `mounts` entry connects a session to a provider's export, and
`configuration.namespace.binds` arranges that tree in the session's view.

For CPUs using a shared OS root, [network-root boot](netroot.md) generates native
boot settings and per-machine namespace files from the inventory.

## Try the example

With native Nix active, copy the example into a writable directory:

```sh
cp -r $nix9/packages/examples/installation /usr/glenda/installation
cd /usr/glenda/installation
bundle=/usr/local/nix/state/gcroots/installation
nix-build default.nix -A build --out-link $bundle
nix9 show --from $bundle
```

Edit `configuration.nix` for the site before selecting a system. The example
advertises `10.0.2.100` through `10.0.2.102` and enables DHCP. Configure DHCP
reservations or static networking to make those addresses reachable. Inventory
addresses describe discovery; native networking settings configure interfaces.

Select the appropriate system on each provisioned machine. On a CPU server
that built the bundle locally:

```sh
installation=`{cat $bundle}
nix9 init cpu
nix9 check $installation/systems/cpu
nix9 select $installation/systems/cpu
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
| `machines.NAME.boot` | Optional [network-root CPU](netroot.md) provider, root name and state directory. |
| `roots.NAME` | [Versioned shared OS root](roots.md), with a pinned seed and optional text files. |
| `machines.NAME.deployment` | CPU connection settings and boot-medium mount for [deployment](deployment.md). |
| `defaults.auth`, `defaults.fs`, `defaults.cpu` | Discovery providers, referenced by inventory key. Each defaults to `null`. |
| `defaults.authdom` | Public authentication domain, default `null`. |
| `ndb` | Shared [NDB module](discovery.md#installation-records), extending generated inventory records. |
| `jobs.NAME` | [Scheduled command](jobs.md) with `scheduler` and `target` inventory keys. |

Declare a session mount by provider and export:

```nix
{
  machines.cpu.mounts.projects = {
    provider = "files";
    export = "projects";
  };
}
```

`export` defaults to the mount's name. The builder derives its address from the
provider's hostname and export port. `mountPoint`, `required`, `timeout` and
`keyPattern` follow [session mount](sharing.md#mount-in-a-session) settings.
The default key pattern selects `defaults.authdom` when set.

To use that mounted tree at a working directory, add a native namespace binding:

```nix
{
  machines.cpu.configuration = {
    directories."/usr/glenda/work" = { };
    namespace.binds = [
      {
        source = "/n/projects";
        target = "/usr/glenda/work";
        create = true;
      }
    ];
  };
}
```

The mount connects to `files`; the binding places its tree at `work` in each
CPU session. `create` permits new files through that binding. File-server
permissions still apply. See [namespace bindings](namespaces.md) for unions
and ordering.

Use `fileSystem = "main"` or `"dump"` to mount a provider's enabled
`services.cwfs` instead of a directory export. The inventory derives native TCP
transport, the port and attach name. See the [storage example](storage.md).

The inventory owns identities, hostnames, primary NDB addresses and these named
mounts. Extend shared discovery through `ndb`; configure per-machine discovery,
includes and DNS through `configuration.services.ndb`.
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
| `discovery` | Shared NDB configuration after module evaluation. |
| `manifest` | Versioned data containing identities, system paths, roles, endpoints, mounts, jobs and dependencies. |
| `overview` | Readable inventory text. `nix9 show` displays it from the built bundle, with optional machine names. |
| `build` | An output containing `manifest.json`, `ndb`, deployment settings under `deployment/` and one closure-path file per machine under `systems/`. Keeping it rooted retains all system closures. |
| `boot.NAME` | Native boot artifacts for each network-root CPU, also copied under `build/boot/NAME`; its `path` file records the standalone artifact for transfer. |
| `roots.NAME` | OS root derivation with `tree/`, base metadata and `publish`; `build/roots/NAME` records its store path. |

Roles come from enabled authentication, CPU and export services. Manifest
dependencies describe authentication and named mounts needed by sessions, plus
remote CPU targets needed when jobs run.
Discovery defaults for CPU and file servers are locations, not boot dependencies.
Ordinary machines may mount each other's exports because their boot namespaces
start independently of user sessions. Network-root CPUs add required `boot`
dependencies on storage and authentication; those providers must boot independently.

The flake exposes the constructor as `lib.mkInstallation` for callers supplying
`lib`, `packages`, `mkDerivation` and `buildEnv`. The native package set binds
these arguments.

Use [deployment commands](deployment.md) to prepare, select and inspect machines
from the bundle. Manual [export/import or signed caches](transport.md#binary-caches)
also work with `nix9 check` and `select`. The configuration expression is
needed only on the builder.
