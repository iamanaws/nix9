# Ownership and cleanup

Keep source fixes with their project, packaging with Nixpkgs, and VM tests here.
These are proposed destinations; upstream status and acceptance are not verified.

| Location | Purpose and owner | When to remove |
| --- | --- | --- |
| [cc9](../pkgs/cc9) | Runtime pin, compiler settings and startup exit-status fix. Runtime fixes belong in cc9; reusable packaging in Nixpkgs. | A pinned runtime preserves numeric exit status without the patch. |
| [cc9-libs](../pkgs/cc9-libs) | Target libraries. Boost's URL fix belongs in Boost; SQLite's native locking needs SQLite/cc9 review. The lock-creation race belongs in 9front's hjfs; SQLite and Nix serialize creation through a kernel service meanwhile. | Updated sources pass the corresponding URL, signing, compression or SQLite checks. |
| [Nix general fixes](../pkgs/nix/patches) | Brotli truncation, store-cache invalidation, cycle detection, non-destructive GC queries and version reporting without opening a store. Candidates for Nix. | The pinned Nix includes equivalent fixes and passes their regressions. |
| [9front.patch](../pkgs/nix/patches/9front.patch) | Platform adaptations and cc9 workarounds. Review each against cc9 before proposing Nix platform support. | Native implementations replace workarounds and pass the affected guest checks. |
| [Store](../pkgs/nix/store-platform.cc) and [build](../pkgs/nix/build-platform.cc) backends | Native roots and builder processes; candidates for Nix platform support. | Upstream supports these operations. Keep unfinished operations explicit. |
| [goken9cc](../pkgs/goken9cc) | Plan 9 C compiler and archive fixes. Candidates for goken9cc. | A pinned compiler passes the ABI and archive tests without them. |

Use Nixpkgs build hooks and package scopes where they fit. The cc9 build still
uses a custom target ABI and prebuilt runtime; it is not a Nixpkgs cross stdenv.
NixBSD is a reference for future system integration, not the owner of cc9 fixes.

Keep refactoring, dependency updates and behavior changes separate. Retire a
patch only after its replacement passes the existing regression. Keep this
inventory brief; detailed evidence belongs with the patch or upstream review.
