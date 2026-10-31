# Remote Nix builders

Run `nix-build` on a terminal and let Nix compile on CPU servers. Nix transfers
missing inputs, schedules derivations and copies outputs back into the terminal's
store. Connections use native `rcpu` authentication and TLS. Each machine keeps
its own writable store at `/usr/local/nix/store`.

## Configure an installation

Declare builders on the machine submitting builds. Names refer to CPU machines
in the [installation inventory](installation.md):

```nix
machines.terminal = {
  builders.build = { maxJobs = 2; };
  builders.batch = { };
  configuration.nix.maxJobs = 0;
};
```

`nix.maxJobs = 0` disables local compilation. Omit it to allow local builds too.
The inventory derives hostnames and the authentication domain. It rejects
unknown providers, disabled CPU services and explicitly denied login users.

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

## Builder settings

| Setting | Default |
| --- | --- |
| `user` | Calling native user. |
| `keyPattern` | Installation authentication domain. |
| `maxJobs` | One concurrent build slot. |
| `speedFactor` | One. Higher values prefer this CPU when capacity is available. |
| `systems` | `[ "x86_64-plan9" ]`. |
| `supportedFeatures`, `mandatoryFeatures` | Empty lists. Mandatory features must be requested by the derivation. |

Set `configuration.nix.systemFeatures` on a builder to match the capabilities
advertised in its `supportedFeatures`. Slot accounting coordinates build clients
on one submitting machine. Separate terminals count their slots independently.
Builders run as the authenticated user; choosing a builder trusts its outputs.

For a standalone `mkSystem`, use `nix.builders.NAME` with the same settings and
an explicit `host`. Its `keyPattern` defaults to an empty string.

## Commands and failures

Override builders for one invocation:

```sh
nix-build /usr/glenda/project --builders 'cpu://build' --max-jobs 0
```

The client needs `pkgs.rcpu` available. System builder declarations include it.
CPU store URLs accept `user@host`, an optional port, and a percent-encoded
`key-pattern` query parameter. The remote login must activate Nix.

Nix skips builders that fail to connect. With no usable builder and local builds
disabled, the build fails. A failed derivation remains a build failure. Interrupting
`nix-build` stops its remote work. `--keep-failed` retains the failed directory on
the CPU server. To build locally for one invocation:

```sh
nix-build /usr/glenda/project --builders '' --max-jobs 1
```

Remote building covers normal input-addressed and fixed-output derivations.
Remote evaluation, floating outputs and remote repair are unsupported.
Each server executes received builds locally, without dispatching them onward.
