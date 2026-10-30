# Shared files and session mounts

Declare a directory on an existing file server and mount it in terminal or CPU
sessions. Exports use native authentication, TLS and 9P. Provision filesystem
accounts and factotum keys through native tools first. See [access](access.md)
for authentication-server configuration and runtime keys.

## Export a directory

On the file server, inside `mkSystem`:

```nix
directories."/usr/glenda/projects".mode = "0750";
services.exports.projects = {
  path = "/usr/glenda/projects";
  allowedUsers = [ "glenda" ];
  readOnly = false;
  keyFile = "/adm/files.keys";
  keyPattern = "dom=lab user=files";
};
```

Use a [directory declaration](configuration.md#persistent-directories) to prepare
the export path, or provision it beforehand. Each export has its own TCP `port`,
defaulting to 17020. Ports must be distinct and cannot overlap `services.listen`,
CPU access or authentication. Export and mount names are lowercase labels.

The server authenticates each connection, checks `allowedUsers`, then runs
packaged `exportfs` as that user. Native filesystem permissions still apply.
`readOnly` defaults to `true` and rejects writes even when those permissions allow
them. Export configuration preserves the directory's contents and metadata.

`keyFile` is an optional, owner-only runtime file of factotum key commands. With
`null`, the export uses provisioned keys. `keyPattern` contains public selection
attributes. Private keys stay outside Nix expressions and the store.

## Mount in a session

On a terminal or CPU server:

```nix
namespace.mounts.projects = {
  address = "tcp!files!17020";
  mountPoint = "/n/projects";
  keyPattern = "dom=lab";
};
```

`mountPoint` defaults to `/n/NAME`. It must be an existing directory; native
`mntgen` normally supplies these paths under `/n`. Mount points cannot overlap.
Runtime paths are absolute strings outside the Nix store. Mounts cannot cover
the local Nix runtime, state or machine configuration. Resolve server names
through [NDB](discovery.md).

Connections use the session's factotum. CPU sessions can use a machine key with
`role=speakfor` when the authentication server grants that identity permission
to represent the user, for example `services.auth.speaksFor.cpu1 = [ "glenda" ];`.
This lets the CPU server access the shared project as the logged-in user.

`required` defaults to `true`. An unavailable required share fails activation and
prevents a new login from executing its command. Set `required = false` to report
the failure and continue with the underlying directory visible. `timeout` bounds
each connection attempt in seconds, defaulting to 10, with a range of 1 to 300.

The connection is private to the session and is not posted in `/srv`. Mounts
apply at login or `. /usr/local/pkg/nix9/system` refresh. Boot and background
service namespaces do not acquire them.

[Directory bindings](namespaces.md) can combine several shares into one ordered
view, including shares from different providers.

## Changes and failures

Export configuration takes effect at the next provider boot. Switching or
rolling back does not change running exports or restore mutable project data.

Session refresh stages new connections before replacing existing mounts. A
failed required connection preserves the session's old mounts. When all shares
are mounted, repeated activation reuses its connections. Existing sessions keep
their own views when another session refreshes.
Provider reboots close existing connections. New logins reconnect.

Selection checks local paths, permissions and conflicts. New connections are
established at login or refresh. Manual mounts at declared destinations and
changes to managed mounts in the current session are rejected. Removing a mount
from the configuration removes its view on the next refresh or login. Removing
an export removes its listener at the next provider boot.
