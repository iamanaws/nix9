# Develop packages

## Cross builds

Run on Linux from the checkout. Replace `PACKAGE` with a name from the
[target table](#build-targets), such as `lua`:

```sh
nix build .#PACKAGE
nix build .#PACKAGE-tests -o result-tests -L
```

Use the second command when the package has a `-tests` target.
The executables run on 9front. The C compiler uses headers and libraries
extracted from the pinned VM image. That first extraction needs KVM available
to Nix builders. Later builds can reuse those store outputs without a VM.
Guest tests require KVM.

## Guest builds

Build the same C source with the guest's own compiler and linker:

```sh
nix build .#hello-c-native -o result-c-native
nix run .#smoke-test-c
```

Nix boots a temporary guest, compiles and tests the program, then returns the
executable to the Nix store. The smoke test runs that executable in a fresh VM.

## C package helper

The flake exports `lib.mkPlan9Program` for small C programs:

```nix
mkPlan9Program {
  name = "my-program";
  sources = [ ./main.c ];
}
```

It compiles each source on Linux, links with the extracted 9front libraries,
checks the executable format, and installs `bin/my-program`. Use `includeDirs`
for extra header directories and `meta` for package metadata. Both `hello-c-cross`
and `sha1sum` use this helper.

APE builds share [compile and link functions](../lib/ape-build.sh).

## Compiler tests

```sh
nix build .#c-abi-tests -o result-abi -L
cat result-abi/results.json
nix build .#ape-tests -o result-ape -L
```

The suite tests arguments, recursion, pointers, callbacks, structures,
floating point and varargs. It compiles the caller and called functions
separately, then runs four builds in 9front:

- Both objects built with 9front's compiler.
- Both objects built and linked on Linux.
- A cross-compiled caller with native functions.
- A native caller with cross-compiled functions.

Every build must pass the same assertions and produce the expected output.
The mixed builds use 9front's linker and check that the two compilers agree
on the calling convention. KVM is required. Nix can reuse a cached test result;
use `nix build .#c-abi-tests --rebuild -L` to rerun it.

The APE test compares cross and guest builds of POSIX C code covering memory,
file I/O, errors, and process execution. It also saves `results.json` and requires KVM.

## Build targets

Run `nix build .#TARGET` from the checkout.

| Target | Build environment | Output |
| --- | --- | --- |
| `hello-plan9` | Linux | Go example for 9front. |
| `hello-c-cross` | Linux | C example for 9front. |
| `hello-c-native` | 9front VM | The same C example, built in the guest. |
| `sha1sum` | Linux | 9front SHA-1 and SHA-2 checksum utility. |
| `sha1sum-tests` | Linux and 9front VM | Checksum and error-handling results. |
| `lua` | Linux | Lua interpreter built with APE. |
| `lua-tests` | Linux and 9front VM | Lua comparison results. |
| `libbz2` | Linux | Static bzip2 library and header for APE. |
| `libbz2-tests` | Linux and 9front VM | Archive and consumer comparison results. |
| `c-abi-cross` | Linux | Compiler test executable and object files. |
| `c-abi-tests` | Linux and 9front VM | Compiler comparison results. |
| `ape-cross` | Linux | POSIX C test executable using APE. |
| `ape-tests` | Linux and 9front VM | APE comparison results. |
| `goken9cc` | Linux | C compiler, assembler, linker and `9ar` archiver. |
| `sysroot` | 9front VM | Extracted headers and libraries. |
| `vm-image` | Linux with KVM | Prepared VM image. |

`nix flake check` validates the Go executable's format and architecture.
Run the package tests to check guest execution. See [test results](validation.md)
and [compiler limitations](feasibility.md#c-toolchain-status).
