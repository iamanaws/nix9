# Remote Nix builders

Run `nix-build` on a terminal and let Nix compile on CPU servers. Nix transfers
missing inputs, schedules derivations and copies outputs back into the terminal's
store. Connections use native `rcpu` authentication and TLS. Each machine keeps
its own writable store at `/usr/local/nix/store`.

## Configure an installation

Declare builders on the machine submitting builds. Names refer to CPU machines
in the [installation inventory](installation.md):

```nix
{
  machines.terminal = {
    builders.build = { maxJobs = 2; };
    builders.batch = { };
    configuration.nix.settings.max-jobs = 0;
  };
}
```

`nix.settings.max-jobs = 0` disables local compilation. Omit it to allow local builds too.
The inventory derives hostnames and the authentication domain. It rejects
unknown providers, disabled CPU services and explicitly denied login users.
It populates `nix.buildMachines` and enables `nix.distributedBuilds` by default.

The three-machine [example](../examples/builders/configuration.nix) contains an
auth server, one build CPU and a terminal:

```sh
cp -r $nix9/packages/examples/builders /usr/glenda/builders-lab
cd /usr/glenda/builders-lab
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/builders-lab
```

Install Nix on each machine and provision networking and
[CPU authentication](access.md). The example needs `build` and `glenda` in the
authentication database, the build server's key in `/adm/cpu.keys`, and Glenda's
client key loaded into the terminal's factotum. Select each system with the
[deployment workflow](deployment.md), then boot the servers and refresh the
terminal session. Builder credentials stay outside Nix expressions and the store.

Build any native project from the terminal:

```sh
. /usr/local/pkg/nix9/system
nix-build /usr/glenda/project
result=`{cat /usr/local/nix/state/gcroots/result}
$result/bin/hello
```

The build log names the selected CPU. Outputs and logs remain on the terminal
after the builder disconnects. Repeating the build reuses valid local outputs.

## Shared-store daemons

A submitting daemon uses its own factotum, independently of the user's login.
Give it a dedicated builder identity and load that identity's private client key
with `nix.daemon.keyFile`. On a shared-store target, the serve protocol needs
trusted daemon access for input-addressed builds:

```nix
{
  machines.build = {
    builders.batch.user = "builder";
    configuration.nix = {
      daemon.keyFile = "/adm/builder.keys";
      settings.max-jobs = 0;
    };
  };
  machines.batch.configuration = {
    services.cpu.allowedUsers = [ "builder" ];
    nix.settings.trusted-users = [ "builder" ];
  };
}
```

Provision the account and key through native authentication. For network-root
CPUs, allow the boot and CPU identities (`glenda` and `batch` in the lab) to speak
for the account through `services.auth.speaksFor` on the auth server.
Trusted access lets that identity control the target store; keep its key private.
Compilation on the shared target still uses the anonymous build identity.
Results return to the submitting store, where users keep their own roots and
profiles. The
[development installation](install.md) includes this arrangement.

## Builder settings

| Setting | Default |
| --- | --- |
| `user` | Calling native user. |
| `keyPattern` | Installation authentication domain. |
| `connectTimeout` | 30 seconds for connection, authentication and serve-protocol setup. `0` disables the deadline. Compilation time is unaffected. |
| `maxJobs` | One concurrent build slot. |
| `speedFactor` | One. Higher values prefer this CPU when capacity is available. |
| `systems` | `[ "x86_64-plan9" ]`. |
| `supportedFeatures`, `mandatoryFeatures` | Empty lists. Mandatory features must be requested by the derivation. |

Set `configuration.nix.settings.system-features` on a builder to match the capabilities
advertised in its `supportedFeatures`. Slot accounting coordinates build clients
on one submitting machine. Separate terminals count their slots independently.
Builders run as the authenticated user; choosing a builder trusts its outputs.

For a standalone `mkSystem`, declare builders in `nix.buildMachines`:

```nix
{
  nix.distributedBuilds = true;
  nix.buildMachines = [
    {
      hostName = "cpu.example.net";
      user = "glenda";
      keyPattern = "dom=example.net";
      systems = [ "x86_64-plan9" ];
    }
  ];
}
```

The native `protocol` defaults to `"cpu"`; `user` and `keyPattern` select CPU
credentials instead of SSH credentials. `system` can specify a single platform
and takes precedence over `systems`. Mandatory features are also included in
the advertised supported features. Setting `nix.distributedBuilds = false`
disables the declared builders; explicit `nix.settings.builders` or command-line
settings can override that choice.

## Commands and failures

Override builders for one invocation:

```sh
nix-build /usr/glenda/project --builders 'cpu://build' --max-jobs 0
```

The client needs `pkgs.rcpu` available. System builder declarations include it.
CPU store URLs accept `user@host`, an optional port, and a percent-encoded
`key-pattern` query parameter. `connect-timeout=SECONDS` overrides the setup
deadline for a direct `cpu://` URL. The remote login must activate Nix.

Nix skips builders that fail to connect. With no usable builder and local builds
disabled, the build fails. A stalled connection reports its CPU store and setup
timeout, then releases the scheduling slot. A failed derivation remains a build failure.
Interrupting `nix-build` stops its remote work. `--keep-failed` retains the failed directory on
the CPU server. To build locally for one invocation:

```sh
nix-build /usr/glenda/project --builders '' --max-jobs 1
```

Remote building covers normal input-addressed and fixed-output derivations.
Remote evaluation, floating outputs and remote repair are unsupported.
Each server executes received builds locally, without dispatching them onward.

## Recover while a builder is unavailable

For the [development installation](install.md), temporarily compile on `build`
by adding this module to the site's `imports`:

```nix
{ lib, ... }:
{
  machines.build.configuration.nix = {
    distributedBuilds = false;
    settings.max-jobs = lib.mkForce 1;
  };
}
```

From the configuration directory on `files`, run `nix9 deploy build`, then
`nix9 status build`. With only [eligible build settings](native.md#shared-store)
changed, `nix-config-reboot no` confirms the daemon uses the selected settings.

Fresh logins compile locally. An existing login or development shell keeps its
client settings: use the one-command override above, or run
`. /usr/local/pkg/nix9/system` before the next build. Cached outputs remain
usable throughout the outage.

When the builder returns, run `nix9-rebuild rollback` at `build`'s owner console
and refresh existing sessions again. Remove the temporary module from
the source before the next deployment. No reboot is needed for these changes.
