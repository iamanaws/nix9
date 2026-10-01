# Toolchain status and next steps

## What works

Nix on Linux cross-compiles Go and C examples for 9front.
It can also build the C program inside a 9front VM and return the
executable to the Nix store. All three executables pass their guest tests.

The Go build uses `GOOS=plan9`, `GOARCH=amd64`, and `CGO_ENABLED=0`.
The C build uses [goken9cc](https://github.com/aryx/goken9cc/tree/e549ce5515ac036ea757d1ebc660686e59ccc35b)
on Linux, with headers and libc extracted from the pinned 9front image.
The guest build uses the image's own `6c` and `6l`.

## C toolchain status

The Linux compiler needs these changes to work with the image's libraries:

- `plan9-archive.patch` changes archive member names from the old Go format's
  64-byte field to 9front's 16-byte field.
- `9front-amd64.patch` restores `REGARG = D_BP`, the first-argument register
  used by 9front's amd64 calling convention. It adds `JMPF` and `MOVQL` linker
  support and matches 9front's opcode numbers and diagnostic names.
- The build defines `_Noreturn` as empty because the compiler cannot parse it.
  This drops the annotation's compiler checks and optimization hints.

The ABI and instruction changes follow the
[9front amd64 definitions](https://github.com/9front/9front/blob/front/sys/src/cmd/6c/6.out.h)
and [linker](https://github.com/9front/9front/tree/front/sys/src/cmd/6l).
The patch reserves the intervening SIMD opcode numbers but does not implement
those instructions.

This compiler is specific to the 9front target. Its changed ABI and archive
format may break upstream's Linux-targeting examples. It is a different compiler
lineage from the guest's compiler, even though both use the same target libraries.

Tests cover one C program and the libc functions it calls. We have not tested
all instructions or libraries, rebuilt libc from source, or established support
for general POSIX packages, C++, or cgo. The prebuilt image remains a bootstrap
dependency. Pinned inputs do not establish bitwise reproducibility of the VM disk.

## Next steps

1. Test floating point, structures, varargs, and more libraries.
2. Build a useful package and add a reusable Nix helper for C builds.
3. Test APE with selected POSIX C packages.
4. Define package metadata and a guest installation layout before adding
   profiles, rollback, or a native stdenv.

The OpenBSD work provides a bootstrap pattern, but its packages and system
modules cannot be reused directly on Plan 9. A stdenv needs working compiler,
archiver, linker, shell, installation tools, and dependency paths.

## Running Nix on Plan 9

Native Nix remains unported. The main questions are:

- Can a C++ compiler and standard library provide the required ABI, exceptions,
  atomics, thread-local storage, and threads?
- Can Nix's dependencies run there, including SQLite, Boost, TLS, compression,
  archive handling, and garbage collection where enabled?
- How will process execution, pipes, signals, file locking, symlinks, permissions,
  and NAR import/export map to Plan 9?
- How will the store database, atomic installation, build users, and isolation work?

Start with a pinned Nix version and audit its dependencies and OS interfaces.
APE may help with some POSIX code, but it does not establish C++ or Nix support.
