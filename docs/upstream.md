# Patches and upstream projects

The port includes source fixes, packaging changes and VM tests. The table below
maps the patches to potential upstream projects and describes what would make
each local patch unnecessary. Destinations without a linked PR are proposals.

| Location | Purpose and owner | When to remove |
| --- | --- | --- |
| [cc9](../pkgs/cc9) | Runtime pin, compiler settings and libc fixes. Runtime fixes belong in cc9. Reusable packaging belongs in Nixpkgs. | A pinned runtime passes the native regressions without patches. |
| [cc9-libs](../pkgs/cc9-libs) | Target libraries. Boost's URL fix belongs in Boost. SQLite's native locking needs review by SQLite and cc9. The lock-creation race is in 9front's hjfs. SQLite and Nix use a kernel service to serialize creation meanwhile. | Updated sources pass the corresponding URL, signing, compression or SQLite checks. |
| [Nix general fixes](../pkgs/nix/patches) | Brotli truncation and store fixes, merged in [#16575](https://github.com/NixOS/nix/pull/16575) and [#16578](https://github.com/NixOS/nix/pull/16578). Repair fallback failure reporting is a Nix candidate. | The pinned Nix includes the fixes and passes their regressions. |
| [cc9 compatibility](../pkgs/nix/patches/cc9-compat.patch) | Nix-side workarounds for environment enumeration, file mappings and coroutine stacks. Runtime fixes belong in cc9. | A pinned runtime passes the process, NAR/import, and cancellation checks without these workarounds. Guard pages need runtime support. |
| [Platform support](../pkgs/nix/patches/9front.patch), [evaluator guards](../pkgs/nix/patches/eval-fetch.patch) and [Meson](../pkgs/nix/patches/meson.patch) | Native locks, notes, store integration, build support and unsupported-feature guards. Portable header fixes merged in [#16582](https://github.com/NixOS/nix/pull/16582). | The pinned Nix includes the header fixes. Other changes need equivalent upstream platform support. |
| [Store](../pkgs/nix/store-platform.cc), [build](../pkgs/nix/build-platform.cc) and [webfs](../pkgs/nix/filetransfer-platform.cc) backends | Native roots, builder processes and cache downloads. Candidates for Nix platform support. | Upstream supports these operations. |
| [goken9cc](../pkgs/goken9cc) | Plan 9 C compiler and archive fixes. Candidates for goken9cc. | A pinned compiler passes the ABI and archive tests without them. |
| [webfs](../pkgs/webfs) | Host-bound certificate pins, live revocation, connection origin separation and HTTPS downgrade rejection. Candidate for 9front. | The pinned webfs enforces an equivalent trust policy and passes the native and cross transport tests. |

The cc9 build uses a custom target ABI rather than a Nixpkgs cross stdenv.
NixBSD provides a reference for future system integration. The regression tests
listed above help assess whether updated dependencies can replace local patches.
