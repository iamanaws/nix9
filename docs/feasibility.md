# Toolchain status and next steps

Nix runs on Linux and builds Go and C programs for 9front. It can also run
builds inside a temporary guest. Native Nix remains unported.

## C toolchain status

Cross builds use [goken9cc](../pkgs/goken9cc), patched for 9front's calling
convention, archive format, and selected instructions. The build drops
`_Noreturn` annotations. This compiler differs from the guest's compiler and
is configured specifically for 9front.

Native Plan 9 and APE runtimes, supporting libraries, and source generators
build on Linux. APE uses GCC for preprocessing. The pinned VM still supplies
sources, headers, and libraries that have not been rebuilt; it also runs tests.
See [package definitions](../pkgs) for the exact build dependencies.

Tests cover selected ABI, POSIX, and library behavior. They do not establish
support for every instruction, general POSIX packages, C++, or cgo. Lua uses
32-bit integers and does not load dynamic C modules. Pinned inputs do not
establish bitwise reproducibility of the VM disk.

## Next steps

Expand compiler and library coverage as packages need it, and define a guest
installation layout before adding profiles, rollback, or a native stdenv.
The OpenBSD work provides a bootstrap pattern, but its system integration
cannot be reused directly on Plan 9.

Running Nix itself requires a C++ toolchain and its dependencies, plus support
for process execution, threads, filesystem semantics, store management, and
build isolation. Start with a pinned Nix version and audit those requirements.
APE provides some POSIX interfaces, but does not establish native Nix support.
