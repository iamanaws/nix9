# Set up a development installation

For a locally provisioned VM version, use the [development lab](lab.md).

The [users example](../examples/users/configuration.nix) connects four machines:

| Machine | Address | Provides |
| --- | --- | --- |
| `auth` | `10.0.2.100` | Authentication for domain `nix9.netroot`. |
| `files` | `10.0.2.101` | CWFS roots, homes, projects and persistent CPU state. |
| `build` | `10.0.2.102` | CPU login and a shared Nix store for Alice and Bob. |
| `batch` | `10.0.2.103` | A second CPU with its own Nix state. |

Use a network where these addresses can reach each other. Separate VMs launched
with the default `run-vm` user network do not form this network. For a VM lab,
connect them through a shared virtual network; reserve the auth/files addresses
in DHCP, or configure their interfaces statically. The two CPUs use static
addresses from the example. Adjust addresses, gateway and devices for your site.

`auth` and `files` need independently bootable 9front installations and the same
[Nix bootstrap](../README.md#quick-start). Set their native boot to `service=cpu`
and `init=/amd64/init -c`. The other CPUs need an amd64 kernel, boot medium and
NVRAM; their OS files will come from CWFS. [PXE](netboot.md) can replace their
local kernel media.

## Keep the configuration

On `files`, create a writable site directory and save this as `default.nix`:

```nix
{ pkgs ? import <nix9> }:
pkgs.mkInstallation ({ lib, ... }: {
  imports = [ <nix9/examples/users/configuration.nix> ];
  name = lib.mkForce "development";
  machines.files.configuration.services.cwfs.deviceMap = lib.mkForce {
    w0 = "/dev/sdG0/data";
    w1 = "/dev/sdH0/data";
  };
})
```

Those devices are examples: choose the cache and worm devices you provision
below. Keep a copy of this file on `auth` for its initial selection. Imports
retain the example's users, delegation, namespaces and CPU settings; add site
overrides here. See [inventory options](installation.md#inventory-and-relationships).

## Provision native state

Use `glenda` as the host owner for this example. Provision NVRAM with
`auth/wrkey`, using domain `nix9.netroot`. Both network-root CPUs boot using
Glenda's authentication key; their CPU service keys are separate. The auth
server's NVRAM key must decrypt its `/adm/keys` database. See the native
[authentication manual](https://github.com/9front/9front/blob/602faae9a52f342a40b086d10b23c71c82dd52d7/sys/man/8/auth).

On `auth`, mount the key database at `/mnt/keys` with
`auth/keyfs -m /mnt/keys /adm/keys`. For a new database, do this after provisioning
NVRAM; for an existing running keyfs, use its mount. Create the identities with
interactive password prompts:

```sh
for(account in glenda alice bob files build batch)
  auth/changeuser $account
```

Prepare these private [factotum key files](access.md#runtime-key-files), using
the matching account passwords and domain:

| File | Identity and roles |
| --- | --- |
| `/adm/files.keys` on `files` | `files`, `server`. |
| `/adm/build.keys` on `files`, for transfer to `build` | `build`, `server` and `speakfor`. |
| `/adm/batch.keys` on `files`, for transfer to `batch` | `batch`, `server` and `speakfor`. |

Make each file owner-only with `chmod 600`. The inventory already declares
the delegation needed for Alice and Bob's file access. On `files`, load Glenda's
client key into its factotum when needed:

```sh
auth/factotum -g 'proto=dp9ik dom=nix9.netroot user=glenda role=client !password?'
```

Follow [initialize empty storage](storage.md#initialize-empty-storage) on `files`
to create the CWFS filesystem, Glenda's account and the root/state directories.
Nix will add Alice, Bob, the project group, their homes and `/projects` from the
declarations.

## Start authentication and storage

At each server's console, in the directory containing `default.nix`, set
`machine=auth` or `machine=files`, respectively:

```sh
. /usr/local/pkg/nix9/activate
nix9 init $machine
nix-build default.nix -A systems.$machine --out-link /usr/local/nix/state/gcroots/initial-system
nix9 select /usr/local/nix/state/gcroots/initial-system
fshalt -r
```

Selection reports missing keys, devices or other prerequisites. Correct them
and repeat selection. After each reboot, run `nix9 status --health` at its
console. Bring both providers up before booting either network-root CPU.

## Prepare the CPUs

On `files`, in the site directory, build and retain the installation:

```sh
. /usr/local/pkg/nix9/system
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/development
installation=`{cat /usr/local/nix/state/gcroots/development}
nix9 show --from $installation
mount -c /srv/cwfs-nix9 /n/site main
root=`{cat $installation/roots/stable}
rc $root/publish /n/site
```

Put the bootstrap archive at `/tmp/bootstrap.tar`. Prepare each CPU and copy
its private service key:

```sh
for(machine in build batch) {
  boot=`{cat $installation/boot/$machine/path}
  rc $boot/prepare /n/site /tmp/bootstrap.tar $installation/systems/$machine
  cp /adm/$machine^.keys /n/site/machines/$machine/adm/cpu.keys
  chmod 600 /n/site/machines/$machine/adm/cpu.keys
}
```

`prepare` initializes separate state, checks the intended machine identity and
stages its system and boot closure. It refuses existing machine state. Keep
the installation root while preparing the machines.

Merge each CPU's `$installation/boot/MACHINE/plan9.ini` into that CPU's boot
medium, preserving its kernel and hardware settings. Provision its NVRAM with
Glenda's key as above. For PXE, [publish and select its boot files](netboot.md#prepare-and-boot)
instead of editing local boot settings.

At each CPU's first console:

```sh
rc /cfg/nix9/initial/finish
fshalt -r
```

The finish command imports the closure and runs normal system selection checks.
If a prerequisite is missing, fix it and rerun the command. Success removes the
import archive; rerunning the command later leaves the selected system alone.
After reboot, run `nix9 status --health`.

## Use and update the installation

The terminal needs Alice's key in factotum and [NDB entries](discovery.md) for
`build`, `batch` and `authdom=nix9.netroot auth=10.0.2.100`. Log in with
`rcpu -u alice -h build`.
Follow [work on either CPU](users.md#work-on-either-cpu) to prepare a shared
project, build it and enter its development shell. Use `batch` in the same way.

For updates, edit the site configuration on `files`, then run there:

```sh
nix9 deploy build batch
nix9 status --health build batch
```

Reboot each CPU explicitly to apply boot services. To undo a CPU system change,
run `nix9-rebuild rollback` at that CPU's console and reboot. User homes, sources
and profiles survive system rollback. [OS root upgrades](roots.md) have their
own selection; [backups](backups.md) protect mutable files.

Auth and file-server changes can be selected at their own consoles with the
same `systems.MACHINE` build above. Stop both network-root CPUs before
rebooting `files`, then start them after it returns. For remote administration
of these providers, enable their [CPU service](access.md#cpu-login) and use
the same deployment interface.
