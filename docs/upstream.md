# Upstream patches

Destinations without a linked PR are proposals.

| Location | Purpose and owner | Remove when |
| --- | --- | --- |
| [cc9](../pkgs/cc9) | Compiler settings and libc fixes belong in cc9; reusable packaging belongs in Nixpkgs. | The pinned runtime passes native regressions without patches. |
| [cc9-libs](../pkgs/cc9-libs) | Boost URL fix; SQLite native locking for SQLite/cc9 review. A kernel service serializes lock creation around an hjfs race. | Updated sources pass the URL, signing, compression and SQLite checks. |
| [Nix fixes](../pkgs/nix/patches) | Brotli truncation and store fixes merged in [#16575](https://github.com/NixOS/nix/pull/16575) and [#16578](https://github.com/NixOS/nix/pull/16578). Repair fallback reporting is a candidate. | The pinned Nix includes the fixes and passes regressions. |
| [cc9 compatibility](../pkgs/nix/patches/cc9-compat.patch) | Environment enumeration, file mapping and coroutine workarounds belong in cc9. | The runtime passes process, NAR/import and cancellation checks without them. Guard pages require runtime support. |
| [Platform support](../pkgs/nix/patches/9front.patch), [evaluator guards](../pkgs/nix/patches/eval-fetch.patch), [Meson](../pkgs/nix/patches/meson.patch) | Native locks, notes, store/build support and feature guards. Header fixes merged in [#16582](https://github.com/NixOS/nix/pull/16582). | The pin includes the headers and upstream provides equivalent platform support. |
| [Store](../pkgs/nix/store-platform.cc), [build](../pkgs/nix/build-platform.cc), [webfs](../pkgs/nix/filetransfer-platform.cc) backends | Native roots, builder processes and cache downloads for Nix. | Upstream supports these operations. |
| [goken9cc](../pkgs/goken9cc) | Plan 9 compiler ABI and archive fixes. | The pin passes ABI/archive tests without patches. |
| [webfs](../pkgs/webfs) | Host-bound pins, live revocation, connection origin separation and HTTPS downgrade rejection for 9front. | Native and cross transport tests pass with an equivalent upstream trust policy. |
| [Native archives](../pkgs/disk-archive/errors.patch) | Failure status, truncated reads, checked writes and path bounds for 9front's mkfs/mkext. | The pinned tools reject incomplete archives and report skipped files and extraction failures. |

cc9 uses a custom target ABI rather than a Nixpkgs cross stdenv.
