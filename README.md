# nix9

nix9 brings Nix to Plan 9, with 9front as the tested system.
Native `nix-instantiate` evaluates expressions and `nix-store` builds packages,
verifies outputs and manages the store. Packages can also cross-compile on Linux.

The project explores a basic Nix interface built on Plan 9 mechanisms.

This is experimental. Builds do not have a full sandbox, and the modern `nix`
CLI and flakes are not available in the guest.
See [test coverage](docs/validation.md) and [limitations](docs/feasibility.md).

## Quick start

On x86_64 Linux with KVM and Nix flakes enabled, run from the checkout.
Your user and Nix builders need access to `/dev/kvm`.
In one terminal, prepare the VM and serve the native Nix package:

```sh
nix build .#vm-image -o result-vm
nix build .#nix-package -o result-nix-package
nix run .#setup-vm
nix develop -c python -m http.server 8000 --bind 127.0.0.1
```

Leave the server running. In another terminal, from the same checkout:

```sh
nix run .#run-vm
```

Press Enter at the boot arguments and user prompts. Wait for the `term%` shell.
A missing-display message from `rio` is expected. Run inside the VM:

```rc
ip/ipconfig ether /net/ether0
hget -o /tmp/nix.tar http://10.0.2.2:8000/result-nix-package
cd / && tar xf /tmp/nix.tar
. /usr/local/pkg/nix-2.34.8/activate
nix-instantiate --eval --expr '6 * 7'
```

The result is `42`. Next, [build a package natively](docs/development.md#native-nix).
The disk persists. Later, run only `run-vm` and activate Nix again.
Keep `result-vm` to retain the backing image. Run `fshalt` before stopping QEMU
with Ctrl-C. The host HTTP server can stop after installation.

## Documentation

- [Run the VM](docs/vm.md): persistent disks and package installation.
- [Develop packages](docs/development.md): cross-compilation, native builds and helpers.
- [Test coverage](docs/validation.md).
- [Status and limitations](docs/feasibility.md).
