# CPU access and authentication

These modules configure native services on an existing CPU server. Provision
`service=cpu`, CPU init and NVRAM through the native tools first. Login also
requires [file-server identities](users.md). See [boot integration](configuration.md#boot-integration).

## CPU login

Inside `mkSystem`:

```nix
{
  services.cpu = {
    enable = true;
    allowedUsers = [ "glenda" ];
    keyFile = "/adm/cpu.keys";
    keyPattern = "dom=lab user=cpu1";
  };
}
```

This serves authenticated, encrypted `rcpu` connections on TCP 17019. The
allowed-user check runs after authentication and before executing client commands.
The list must be nonempty. Users get their native login namespace and the
selected system's packages, generated files and session services.

`keyFile` is an optional runtime file of factotum key commands, loaded into the
boot factotum. It must be readable only by its owner. With `null` (the default),
the service uses keys already provisioned in factotum. `keyPattern` selects a
server key by public attributes; its default is empty. Put secret attributes in
the runtime file, never in Nix expressions or generated system files.

From a client with its key loaded and the authentication server discoverable:

```sh
rcpu -u glenda -h cpu1
rcpu -u glenda -h cpu1 -c 'nix-build /mnt/term/path/to/project'
```

`pkgs.rcpu` provides the client scripts and TLS tools, with packaged `exportfs`.
The server module selects its packaged TLS server. Early-boot factotum remains
part of native startup.

## Runtime key files

A key file contains factotum control commands. For a CPU named `build`, these
entries allow server authentication and delegated file access:

```text
key proto=dp9ik dom=nix9.netroot user=build role=server !password='ACCOUNT-PASSWORD'
key proto=dp9ik dom=nix9.netroot user=build role=speakfor !password='ACCOUNT-PASSWORD'
```

Replace the identity, domain and password with the provisioned account's values.
Keep the file outside the store, owned by the host owner with mode `0600`.
The `server` entry is sufficient for a file server; CPUs also use `speakfor` for
users' filesystem authentication. The auth server must grant the corresponding
delegation in `services.auth.speaksFor`. See native
[factotum key management](https://github.com/9front/9front/blob/602faae9a52f342a40b086d10b23c71c82dd52d7/sys/man/4/factotum).

## Authentication server

```nix
{
  services.auth = {
    enable = true;
    keyDatabase = "/adm/keys";
    speaksFor.terminal1 = [ "glenda" ];
  };
}
```

This starts packaged `keyfs` and serves authentication tickets on TCP 567.
`keyDatabase` defaults to `/adm/keys` and must already exist. It uses the machine's
provisioned NVRAM key for decryption. Owner and group access are permitted; access
for others is rejected. Manage accounts and keys with native tools, using the
owner-only `/srv/nix9-keys` service to mount the running database. They are
mutable data and are not restored by configuration rollback. Optional
`requiredUsers` checks that named identities have enabled, unexpired dp9ik keys.
See [users and groups](users.md#authentication).

`speaksFor` maps authentication identities to the users they may represent. The
example lets `terminal1` obtain tickets for `glenda`. The default grants no
delegation; an identity may always authenticate as itself. Names are literal,
with no wildcards. The generated policy is visible only to the managed
authentication listener.

The two modules are independent: a CPU server can use a separate authentication
server, and an authentication server need not offer CPU login. Configure service
locations through [NDB](discovery.md).

## Selection and startup

Service configuration and access policy take effect at the next CPU-server boot.
Switching or rolling back changes what future logins see in their system
environment; existing sessions keep their namespaces. Key and account changes
made through native tools are separate from system selection.

Selection checks runtime file paths, permissions and manual CPU-port conflicts.
Runtime key paths must be absolute strings outside the Nix store. Startup checks
again before starting the managed listeners. Missing files or conflicts prevent
managed access startup. Repeated startup does not create another listener.

The modules share the native listener integration with `services.listen`.
Ordinary manual TCP services keep their scripts and namespaces. The authentication
module supplies its own trusted service directory and replaces the native
authentication-server startup. Remove a manual `tcp17019` service or namespace
from the active service directory before enabling managed CPU access.

To disable a role, disable its module and remove its other settings. The next boot
removes its managed service; native services still follow the site's startup
configuration.
