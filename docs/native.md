# Native Nix

[Install the bootstrap](../README.md#quick-start) first. Guest examples use rc.
Activate Nix and build a package from the bundled set:

```sh
. /usr/local/pkg/nix9/activate
roots=/usr/local/nix/state/gcroots
nix-build $nix9/packages -A fortune --out-link $roots/package
result=`{cat $roots/package}
$result/bin/fortune
```

For a local project, run `nix-build` in its directory. See
[package development](development.md) for recipes and `nix-shell`.

## Environments

Copy [environment.nix](../examples/environment.nix) into the guest, then run:

```sh
nix-build environment.nix --out-link $roots/environment
environment=`{cat $roots/environment}
touch /tmp/nix9.lua
. $environment/activate
lua /tmp/nix9.lua
```

`buildEnv` combines packages, merges command subdirectories such as `bin/ip`, and
rejects duplicate command paths. Its optional
`files` maps existing absolute paths to text. Activation binds those files in the
shell's namespace; switching environments reveals the originals.

Run `$environment/session COMMAND ARGS...` for a private session, or omit the
command for interactive rc. The optional `namespace` rc snippet runs after
session activation, not when sourcing `activate`. Session processes keep the
environment rooted; their mounts disappear when the last process exits.
The bundled [ramfs example](../examples/ramfs) demonstrates this:

```sh
nix-build $nix9/ramfs --out-link $roots/ramfs
environment=`{cat $roots/ramfs}
$environment/session rc $nix9/ramfs/run.rc
```

## Generations and updates

Use `nix-profile` to retain environments:

```sh
nix-profile $roots/environment set $environment
nix-profile $roots/environment list
```

`nix-profile` is this port's generation manager, using Plan 9 root files.
It is separate from the upstream `nix profile` CLI.

`set` retains the previous selection and reuses an existing generation when
possible. After selecting another environment, `rollback` returns to the
preceding generation; `delete NUMBER` releases an inactive one for GC.
Build updates with a separate `--out-link` before selecting them.

Add these lines to `$home/lib/profile` for login activation:

```sh
. /usr/local/pkg/nix9/activate
. $nix9/packages/profile /usr/local/nix/state/gcroots/environment
```

Source the second line after selection changes to refresh the current shell.

To publish recipes, build `nix build .#native-package-source` on Linux and serve
its `packages.tar.gz`. Copy the generated `update.nix` into the guest, change its
URL, and edit `paths` to select packages. It pins the archive's unpacked hash.
With [webfs mounted](transport.md), run:

```sh
nix-build update.nix --out-link $roots/update &&
  nix-profile $roots/environment set `{cat $roots/update}
. $nix9/packages/profile $roots/environment
```

Recipe updates keep the installed Nix commands. Fetched recipes remain usable
offline until GC removes them.

## Complete releases

Release generations retain Nix itself and its package set:

```sh
nix-build /usr/local/pkg/nix9/release.nix --out-link $roots/release
nix-profile $roots/nix9 set `{cat $roots/release}
. /usr/local/pkg/nix9/activate
```

After installing a new bootstrap archive, repeat these commands to upgrade.
Unpacking preserves the existing release selection. To return to the previous
release, run `nix-profile $roots/nix9 rollback` and source the activation file.

Releases, environments and [system configurations](configuration.md) have
separate profiles.

## Shared-store prototype

`native-shared-store-tests` exercises two authenticated users sharing one CPU's
store through Nix's worker protocol. A native listener uses factotum and TLS;
the store remains writable only by its owner. Builds run as Plan 9's anonymous
`none` identity in a fresh namespace with a private RAMFS. The owner imports
their outputs, then revokes that filesystem, including descriptors retained by
detached processes. Builders cannot access the owner's credentials; the kernel
also restricts the anonymous identity's access to other processes.

The prototype supports `nix-build --no-out-link` through an explicitly selected
daemon connection, with one build at a time per store. This is an ownership
boundary, not a full sandbox. Profiles, development shells, managed startup and
multi-CPU use are not integrated yet. The [test](../tests/native_shared_store.py)
provisions disposable accounts and runtime keys.

Recovery tests cover repeated timeouts, cancellation and killed clients, checking
process cleanup and queued builds without restarting the listener. An earlier
malformed timeout reply has not recurred; its exact cause remains unconfirmed.

## Store maintenance

The machine store is `/usr/local/nix/store`. Roots are files containing store paths,
rather than symlinks. `nix-build` defaults to
`/usr/local/nix/state/gcroots/result`; `--no-out-link` creates no permanent root.
Running programs outside a Nix build need an explicit root.

| Task | Command |
| --- | --- |
| Retain an existing output | `nix-store --realise --add-root $roots/package $result` |
| Compare a rebuild without replacing the output | `nix-build --check` |
| Collect unused paths after removing their roots | `nix-store --gc` |
| Check contents and remove missing, unreferenced registrations | `nix-store --verify --check-contents` |
| Restore an output from a cache or available derivation | `nix-store --repair-path PATH` |
| Check and repair a package and its dependencies | `nix-build --repair` |

Stop other store clients before GC, verification or repair. All clients must
share the canonical store path and kernel service namespace.

After an unclean shutdown, reboot, activate Nix, and run `nix-store --recover`
before any store client opens the store. Recovery removes stale lock markers
and lets SQLite recover its journal. Then rebuild or repair interrupted outputs
and verify them. Interrupted replacements need another repair after recovery.
Restore a damaged SQLite database from backup.
See [downloads and caches](transport.md#binary-caches) for cache configuration.
