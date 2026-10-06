# Ownership and cleanup

Keep source fixes with their project, packaging with Nixpkgs, and VM tests here.
These are proposed destinations; upstream status and acceptance are not verified.

| Location | Purpose and owner | When to remove |
| --- | --- | --- |
| [cc9](../pkgs/cc9) | Runtime pin, compiler settings and libc fixes. Runtime fixes belong in cc9; reusable packaging in Nixpkgs. | A pinned runtime passes the native regressions without patches. |
| [cc9-libs](../pkgs/cc9-libs) | Target libraries. Boost's URL fix belongs in Boost; SQLite's native locking needs SQLite/cc9 review. The lock-creation race belongs in 9front's hjfs; SQLite and Nix serialize creation through a kernel service meanwhile. | Updated sources pass the corresponding URL, signing, compression or SQLite checks. |
| [Nix general fixes](../pkgs/nix/patches) | Brotli truncation, store-cache invalidation, cycle detection, non-destructive GC queries and version reporting without opening a store. Candidates for Nix. | The pinned Nix includes equivalent fixes and passes their regressions. |
| [cc9 compatibility](../pkgs/nix/patches/cc9-compat.patch) | Nix-side workarounds for environment enumeration, file mappings and coroutine stacks. Runtime fixes belong in cc9. | A pinned runtime passes the process, NAR/import, and cancellation checks without these workarounds; guard pages need runtime support. |
| [Platform support](../pkgs/nix/patches/9front.patch) and [Meson](../pkgs/nix/patches/meson.patch) | Native locks, notes, store integration, build support and unsupported-feature guards. Platform support and portable header fixes are candidates for Nix. | Upstream provides equivalent platform support. Keep guards until the excluded operations work. |
| [Store](../pkgs/nix/store-platform.cc) and [build](../pkgs/nix/build-platform.cc) backends | Native roots and builder processes; candidates for Nix platform support. | Upstream supports these operations. Keep unfinished operations explicit. |
| [goken9cc](../pkgs/goken9cc) | Plan 9 C compiler and archive fixes. Candidates for goken9cc. | A pinned compiler passes the ABI and archive tests without them. |

Use Nixpkgs build hooks and package scopes where they fit. The cc9 build still
uses a custom target ABI; it is not a Nixpkgs cross stdenv.
NixBSD is a reference for future system integration, not the owner of cc9 fixes.

Keep refactoring, dependency updates and behavior changes separate. Retire a
patch only after its replacement passes the existing regression. Keep this
inventory brief; detailed evidence belongs with the patch or upstream review.
