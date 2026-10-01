# Develop packages

## Cross builds

Run these commands on Linux from the checkout:

```sh
nix build .#hello-c-cross -o result-c-cross
nix run .#smoke-test-c-cross
nix build .#hello-plan9 -o result-go
nix run .#smoke-test
```

The executables run on 9front. The C compiler uses headers and libraries
extracted from the pinned VM image. That first extraction needs KVM available
to Nix builders. Later builds can reuse those store outputs without a VM.

## Guest builds

Build the same C source with the guest's own compiler and linker:

```sh
nix build .#hello-c-native -o result-c-native
nix run .#smoke-test-c
```

Nix boots a temporary guest, compiles and tests the program, then returns the
executable to the Nix store. The smoke test runs that executable in a fresh VM.

## Build targets

Run `nix build .#TARGET` from the checkout.

| Target | Build environment | Output |
| --- | --- | --- |
| `hello-plan9` | Linux | Go example for 9front. |
| `hello-c-cross` | Linux | C example for 9front. |
| `hello-c-native` | 9front VM | The same C example, built in the guest. |
| `goken9cc` | Linux | Patched C compiler, assembler and linker. |
| `sysroot` | 9front VM | Extracted headers and libraries. |
| `vm-image` | Linux with KVM | Prepared VM image. |

`nix flake check` validates the Go executable's format and architecture.
Run the smoke tests above to check guest execution. See [test results](validation.md)
and [compiler limitations](feasibility.md#c-toolchain-status).
