# nix9

Build programs for 9front with Nix, using
[9front-in-a-box](https://github.com/majiru/9front-in-a-box) for the VM.
Go and C examples cross-compile on Linux and pass tests inside 9front.

This is experimental. Packages cross-compile on Linux. On 9front, `nix-store`
adds and queries paths, and `nix-eval` evaluates expressions. Native Nix builds
remain future work.
See [test coverage](docs/validation.md) and [limitations](docs/feasibility.md).

## Quick start

On x86_64 Linux with KVM and Nix flakes enabled, run from the checkout:

```sh
nix build .#hello-c-cross
nix run .#smoke-test-c-cross
```

The build produces `result/bin/hello-c`. The test runs it in a fresh 9front VM
and checks file I/O and child processes. The first build extracts the required
headers and libraries from the VM image.

## Documentation

- [Run the VM](docs/vm.md): setup, console and persistent disk.
- [Develop packages](docs/development.md): builds, tests and package helpers.
- [Test coverage](docs/validation.md).
- [Toolchain status and next steps](docs/feasibility.md).
