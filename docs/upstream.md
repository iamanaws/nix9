# Ownership and cleanup

Keep source fixes with their project, packaging with Nixpkgs, and VM tests here.
These are proposed destinations; upstream status and acceptance are not verified.

| Location | Purpose and owner | When to remove |
| --- | --- | --- |
| [cc9](../pkgs/cc9) | Runtime pin, compiler settings and startup exit-status fix. Runtime fixes belong in cc9; reusable packaging in Nixpkgs. | A pinned runtime preserves numeric exit status without the patch. |
| [cc9-libs](../pkgs/cc9-libs) | Target libraries. Boost's URL fix belongs in Boost; SQLite's native locking needs SQLite/cc9 review. Library adaptations belong with each library. | Updated sources pass the corresponding URL, signing, compression or SQLite checks. |
| [Nix general fixes](../pkgs/nix/patches) | Brotli truncation, store-cache invalidation, cycle detection and version reporting without opening a store. Candidates for Nix. | The pinned Nix includes equivalent fixes and passes their regressions. |
| [9front.patch](../pkgs/nix/patches/9front.patch) | Platform adaptations and cc9 workarounds. Review each against cc9 before proposing Nix platform support. | Native implementations replace workarounds and pass the affected guest checks. |
| [store-platform.cc](../pkgs/nix/store-platform.cc) | Native temporary roots and explicit errors for unfinished operations. | Implement each operation; do not upstream unsupported-operation placeholders as completed support. |
| [goken9cc](../pkgs/goken9cc) | Plan 9 C compiler and archive fixes. Candidates for goken9cc. | A pinned compiler passes the ABI and archive tests without them. |

Use Nixpkgs build hooks and package scopes where they fit. The cc9 build still
uses a custom target ABI and prebuilt runtime; it is not a Nixpkgs cross stdenv.
NixBSD is a reference for future system integration, not the owner of cc9 fixes.

Keep refactoring, dependency updates and behavior changes separate. Retire a
patch only after its replacement passes the existing regression. Keep this
inventory brief; detailed evidence belongs with the patch or upstream review.
