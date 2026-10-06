# Patches and upstream projects

The port includes source fixes, packaging changes and VM tests. The table below
maps the patches to potential upstream projects and describes what would make
each local patch unnecessary. These destinations are proposals; upstream status
and acceptance have not been verified.

| Location | Purpose and owner | When to remove |
| --- | --- | --- |
| [cc9](../pkgs/cc9) | Runtime pin, compiler settings and libc fixes. Runtime fixes belong in cc9. Reusable packaging belongs in Nixpkgs. | A pinned runtime passes the native regressions without patches. |
| [cc9-libs](../pkgs/cc9-libs) | Target libraries. Boost's URL fix belongs in Boost. SQLite's native locking needs review by SQLite and cc9. The lock-creation race is in 9front's hjfs. SQLite and Nix use a kernel service to serialize creation meanwhile. | Updated sources pass the corresponding URL, signing, compression or SQLite checks. |
| [Nix general fixes](../pkgs/nix/patches) | Brotli truncation, store-cache invalidation, cycle detection, non-destructive GC queries and version reporting without opening a store. Candidates for Nix. | The pinned Nix includes equivalent fixes and passes their regressions. |
| [cc9 compatibility](../pkgs/nix/patches/cc9-compat.patch) | Nix-side workarounds for environment enumeration, file mappings and coroutine stacks. Runtime fixes belong in cc9. | A pinned runtime passes the process, NAR/import, and cancellation checks without these workarounds. Guard pages need runtime support. |
| [Platform support](../pkgs/nix/patches/9front.patch) and [Meson](../pkgs/nix/patches/meson.patch) | Native locks, notes, store integration, build support and unsupported-feature guards. Platform support and portable header fixes are candidates for Nix. | Upstream provides equivalent platform support, including guards for unsupported operations. |
| [Store](../pkgs/nix/store-platform.cc) and [build](../pkgs/nix/build-platform.cc) backends | Native roots and builder processes. Candidates for Nix platform support. | Upstream supports these operations. |
| [goken9cc](../pkgs/goken9cc) | Plan 9 C compiler and archive fixes. Candidates for goken9cc. | A pinned compiler passes the ABI and archive tests without them. |

The cc9 build uses a custom target ABI rather than a Nixpkgs cross stdenv.
NixBSD provides a reference for future system integration. The regression tests
listed above help assess whether updated dependencies can replace local patches.
