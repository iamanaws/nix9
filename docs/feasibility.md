# Native Nix feasibility

Packages cross-compile on Linux. An experimental native `nix-store` adds files
and directories and queries metadata on 9front. `nix-instantiate` evaluates expressions
as JSON and instantiates derivations. Native builds use upstream Nix’s scheduler
with a 9front process backend. They support input-addressed outputs and flat or
recursive fixed outputs, without sandboxing or a diverted store. Partial rebuilds
preserve valid outputs; fixed-output hash mismatches are discarded. The evaluator uses upstream’s
no-GC mode for short-lived runs. Native `fetchurl` uses 9front’s `webfs` and verifies
the content hash. Its HTTPS transport does not validate server certificates;
content integrity relies on the pinned hash. Signed `file://` binary caches support
native substitution. Flakes and evaluator network fetchers remain unported.

Our patched [goken9cc](../pkgs/goken9cc) rebuilds C runtimes and libraries on
Linux; APE uses GCC for preprocessing. The VM supplies remaining sources,
headers, and libraries. These builds do not establish C++ or full POSIX support.

## Audit

Target: [Nix 2.34.8][nix], commit `f3f1c3c5b8ad91850e0f7c590cf177f7ab022024`.
Its Meson files require C++23, Boost 1.87 or later, OpenSSL, libarchive,
libsodium, Brotli, BLAKE3, curl 8.17 or later, SQLite, libgit2, JSON and TOML
libraries. Boehm GC, S3 support, and Linux seccomp can be disabled.

| Area | Evidence and remaining work |
| --- | --- |
| C++ | Nix archive, streaming, hashing, compression, URL parsing, and signing code runs on 9front with cc9. Libutil and libstore build through upstream Meson; the modern `nix` CLI remains unported. The build omits libarchive disk APIs; coroutine stacks and libsodium allocations lack guard pages. |
| ABI | cc9 uses the SysV ABI. Our existing Plan 9 and APE archives cannot be linked into it; Nix dependencies need separate builds. |
| Filesystem | The [NAR probe](../tests/nar.py) round-tripped Nix 2.34.8 archives byte-for-byte, including links and control characters in names. Regular files and directories also survived extraction and re-archiving. Links and unsupported names stay in archives; extraction rejects them before writing. Native symlink resolution is still missing. |
| Store | `LocalStore` imports regular files and directories from NARs, validates hashes, and queries metadata and references. Temporary roots clean up on close or process death. Clients share the store using [native locks](../pkgs/cc9-libs/plan9-lock.c) and rollback journals. They must use the same canonical store path and kernel service namespace, with one connection per store per process. GC and schema changes require exclusive client access. Explicit GC retains permanent roots and their dependencies. Automatic GC, runtime root discovery, indirect roots, profiles, repair, WAL and multiuser mode remain unsupported. Offline recovery of interrupted builds and SQLite transactions is tested; torn writes remain untested. |
| Processes and locks | Child processes support pipes, PATH, environments, wait and kill. Interrupt/hangup notes cancel at Nix interruption checks. Exclusive path locks pass contention, fork/exec and killed-holder tests; server crashes may leave markers. Generic file locks, credentials, process groups, signal threads and PTYs remain unsupported. |

The [Nix build](../pkgs/nix) uses the pinned [cc9 runtime](../pkgs/cc9) and
[target libraries](../pkgs/cc9-libs). The cc9 runtime, libc++ and libm are built from pinned sources. See [patch ownership](upstream.md).
Builds run on Linux and tests in a disposable VM:

```sh
nix build .#nix-util-tests -L
```

[nix]: https://github.com/NixOS/nix/tree/f3f1c3c5b8ad91850e0f7c590cf177f7ab022024
