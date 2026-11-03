# Users and groups

Plan 9 file servers keep one `/adm/users` table. Each entry defines both a user
and a group, with an on-disk ID, a group leader and members. Authentication
servers keep passwords and keys separately.

Declare shared entries in `mkInstallation`:

```nix
{
  users = {
    alice = { id = 1010; home = "/usr/alice"; };
    bob = { id = 1011; home = "/usr/bob"; };
    project = {
      id = 1012;
      leader = "alice";
      members = [ "alice" "bob" ];
    };
  };
  machines.files.configuration.services.cwfs.directories."/projects" = {
    owner = "alice";
    group = "project";
    mode = "0770";
  };
  machines.auth.configuration.services.auth.requiredUsers = [ "alice" "bob" ];
}
```

The inventory shares these entries with every enabled CWFS server. A standalone
`mkSystem` uses the same table under `services.cwfs.users`. Per-server entries
can extend it. CPU login and export policies still declare their allowed users.
See the [four-machine example](../examples/users/configuration.nix): an
authentication server, a file server and two network-root CPUs, `build` and
`batch`. Both CPUs expose the same private homes and `/n/projects`, and make
the declared packages available to Alice and Bob.

## File-server identities

IDs must be distinct integers from 1 to 32767. Use the IDs already assigned when
adopting existing accounts. A declared name cannot change ID, and an ID cannot
be reassigned to another name. Native `adm` and `none` entries remain untouched.
Names use letters, digits, underscores or dots and are shorter than 28 bytes.

`leader` defaults to the entry's name. Set it to `null` for the native policy
where any member may lead the group. `members` defaults to an empty list and
sets the complete membership of a declared entry. Leaders, members and directory
owners must exist in the merged table; they may be provisioned native entries.

`home` defaults to `null`. Setting it prepares a directory owned by that user
and group, with `homeMode = "0700"` by default. Directory declarations preserve
contents and set metadata on the named directory, without recursively changing
its files. `services.cwfs.directories` uses the same mode, owner and group fields
as system directories, but requires both owner and group.

Network-root CPUs append the provider's `/usr` to their machine-specific `/usr`
when the inventory declares homes. A native `/usr/NAME` home is then shared
between CPUs. Machine-specific files take precedence, including each CPU's
`/usr/local/nix`. Other boot arrangements need their own native home bindings.

## Authentication

Provision passwords with native tools on the authentication server. To administer
the running managed database, mount its owner-only service:

```sh
mount -c /srv/nix9-keys /mnt/keys
auth/changeuser alice
auth/changeuser bob
```

Use the provisioning keyfs mount before the service's first boot.
`services.auth.requiredUsers` checks for enabled, unexpired dp9ik keys at
selection and startup. It also accepts machine identities. It creates no keys
or authentication accounts. Passwords, NVRAM and private runtime files stay
outside Nix expressions and the store. See [authentication](access.md).

Native root mounts also need delegation for their NVRAM identity. The example
uses `glenda` for root boot, so its authentication policy lets `glenda` and
the CPU service identities `build` and `batch` represent Alice and Bob. A CPU
service's `keyPattern` selects its login key; it does not select the key for native
root mounts.

## Work on either CPU

With Alice's client key available to factotum, use ordinary CPU connections:

```sh
rcpu -u alice -h build
```

Her files under `/usr/alice` also appear when she logs into `batch`. The project
directory belongs to Alice and the `project` group. As Alice, prepare the shared
example once:

```sh
mkdir -p /n/projects/hello
cp $nix9/packages/examples/workstation/project/* /n/projects/hello/
chmod 770 /n/projects/hello
chmod 660 /n/projects/hello/*
```

Both users can edit these sources on either CPU and run configured system
packages such as `fortune`. Enable [shared-store user builds](native.md#shared-store)
on an individual CPU through `services.nixStore`. Updating one CPU leaves the
other CPU and shared homes in place.

## Changes and recovery

CWFS applies the table and directory metadata at file-server boot, before serving
clients. Selection checks an account-capable CWFS server through its owner-only
`/srv/cwfs-nix9.users` console without changing it. Before the first such boot,
checks against existing IDs happen during startup.
The filesystem and its initial `/adm/users` must already be provisioned.
Stop network-root CPUs before restarting their root provider, then boot them
after the file server returns.

Undeclared accounts and their memberships remain in the native table. Removing a
declaration never deletes an account, its home or its files. To revoke access,
change declared memberships and service policies and disable the authentication
key through native tools. Removing a name from `requiredUsers` only removes its
provisioning check.

Rollback restores the older generation's declared memberships and directory
metadata at the next file-server boot. Accounts added later, file contents and
authentication keys remain. Retire accounts and reclaim IDs through native
administration after checking file ownership.

The importer keeps the preceding table at `/adm/users.nix9.bak`. Replacement
uses native renames and is not atomic. If interrupted with `/adm/users` missing,
recover the backup through the CWFS console before restarting managed storage.
