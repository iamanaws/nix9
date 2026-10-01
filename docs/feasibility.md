# Toolchain status and next steps

## What works

Nix on Linux cross-compiles Go and C examples for 9front.
It also cross-compiles 9front's `sha1sum` using a shared C package helper.
It can also build the C program inside a 9front VM and return the
executable to the Nix store. The examples pass their guest tests.

The Go build uses `GOOS=plan9`, `GOARCH=amd64`, and `CGO_ENABLED=0`.
The C build uses [goken9cc](https://github.com/aryx/goken9cc/tree/e549ce5515ac036ea757d1ebc660686e59ccc35b)
on Linux, with rebuilt libc and headers extracted from the pinned 9front image.
The guest build uses the image's own `6c` and `6l`.

## C toolchain status

The Linux compiler needs these changes to work with the image's libraries:

- `plan9-archive.patch` changes archive member names from the old Go format's
  64-byte field to 9front's 16-byte field and fixes handling of full-length names.
- `9front-amd64.patch` restores `REGARG = D_BP`, the first-argument register
  used by 9front's amd64 calling convention. It adds `JMPF` assembler and linker
  support, `MOVQL` linker support, and matches 9front's opcode numbers and names.
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

The C tests cover file and process operations, arguments, recursion, pointers,
callbacks, structure passing and returns, floating point, and varargs.
Native, cross-compiled and mixed-compiler builds pass the same assertions.
See [compiler tests](development.md#compiler-tests).

APE cross and guest builds pass memory, file I/O, error, and process tests.
The [cross build](../tests/ape/default.nix) uses GCC only for preprocessing,
redirects absolute header paths, and links `libap` explicitly.

Lua 5.4.8 passes cross and guest tests with APE's POSIX interfaces, including
subprocess pipes and exit status. It uses 32-bit integers; dynamic C modules
remain disabled.

libbzip2 and APE's `libap` and `libbsd` build from source using `9ar`, including
APE startup assembly and syscall stubs. APE tests, Lua, and the libbzip2 consumer
use the rebuilt runtimes. Native Plan 9 `libc` also builds from source and is used
by the C example, checksum utility, and cross-compiled ABI tests.

The checksum utility also uses rebuilt `libsec`. Its source generation and
compilation run on Linux, using `mpc` built with Plan 9 port compatibility libraries.

We have not tested all instructions or libraries, or established support for
general POSIX packages, C++, or cgo. The prebuilt image remains a bootstrap
dependency. Pinned inputs do not establish bitwise reproducibility of the VM disk.

## Next steps

1. Expand library and compiler coverage as packages expose new requirements.
2. Test APE with packages that need more POSIX interfaces.
3. Define package metadata and a guest installation layout before adding
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
