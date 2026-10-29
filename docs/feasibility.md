# Status and limitations

The port targets [Nix 2.34.8][nix], commit
`f3f1c3c5b8ad91850e0f7c590cf177f7ab022024`.
[Cross-build recipes](../pkgs/nix) compile Nix and its C++ dependencies on Linux
using [cc9](../pkgs/cc9). Native C and Go development work inside 9front.

## Port constraints

| Area | Constraints |
| --- | --- |
| Builds | Upstream Nix scheduling with a 9front process backend. Input-addressed and flat or recursive fixed outputs work. No full sandbox or diverted store; undeclared host files remain accessible. |
| Evaluator | Upstream no-GC mode for short runs. The modern `nix` CLI, flakes and `builtins.fetchGit` are unported. |
| C++ and ABI | cc9 uses the SysV ABI, requiring separate dependencies from Plan 9 and APE archives. The build omits libarchive disk APIs. Coroutine stacks and libsodium allocations lack guard pages. |
| Filesystem | NARs preserve links and unsupported names, but extraction rejects them before writing. Native symlink resolution is missing. |
| Store | Clients must share the canonical store path and kernel service namespace, with one connection per store per process. GC, verification, repair and schema changes require exclusive client access. Permanent roots work; automatic GC, runtime root discovery, indirect roots, `nix-env`, WAL and multiuser mode do not. |
| Processes and locks | Pipes, PATH, environments, wait, kill, exclusive path locks and cancellation notes work. Generic file locks, Unix credential APIs, process groups, signal threads and PTYs are unported. Server crashes may leave lock markers. |
| Machine configuration | [System modules](configuration.md) and [installation inventories](installation.md) use existing bootable machines with local writable stores and generation state. Native tools manage accounts, keys, filesystem ownership, kernels, disks and boot configuration. General namespace composition, scheduled maintenance, backups, graphical workspaces and daemon supervision have no declarative modules yet. |

## Verification limits

[Tests](validation.md) cover native builds, NAR round trips, concurrent clients,
offline recovery and system generations. They do not cover torn writes, abrupt
power loss during initial hook installation or generation selection, external IPv6,
or DHCP renewal through lease expiration.

For download trust restrictions, see [HTTPS policy](transport.md#https-trust).
For local changes and their upstream owners, see [patches](upstream.md).

[nix]: https://github.com/NixOS/nix/tree/f3f1c3c5b8ad91850e0f7c590cf177f7ab022024
