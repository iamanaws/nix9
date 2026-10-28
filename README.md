# nix9

nix9 brings Nix to Plan 9, with 9front as the tested system.
Native `nix-build` builds packages, `nix-instantiate` evaluates expressions,
and `nix-store` verifies outputs and manages the store. Packages can also cross-compile on Linux.

The project explores a basic Nix interface built on Plan 9 mechanisms.

This is experimental. Builds do not have a full sandbox, and the modern `nix`
CLI and flakes are not available in the guest.
See [test coverage](docs/validation.md) and [limitations](docs/feasibility.md).

## Quick start

On x86_64 Linux with KVM and Nix flakes enabled, run from the checkout.
Your user and Nix builders need access to `/dev/kvm`.
Accept the flake's cache settings when prompted to use `nix9.cachix.org`.
In one terminal, prepare the VM and serve the bootstrap archive:

```sh
nix build .#vm-image -o result-vm
nix build .#native-bootstrap -o result-native-bootstrap
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
cd / && hget http://10.0.2.2:8000/result-native-bootstrap | tar x
. /usr/local/pkg/nix9/activate
roots=/usr/local/nix/state/gcroots
nix-build $nix9/environment.nix --out-link $roots/environment
environment=`{cat $roots/environment}
. $environment/activate
echo -n abc | sha1sum
```

The archive includes Nix, a pinned package set and a signed native cache.
If Cachix has no copy, this step builds the native packages in a VM.
Try a C project with the cached toolchain:

```rc
mkdir /tmp/hello
cp $nix9/hello/* /tmp/hello
cd /tmp/hello
nix-shell default.nix --run 'mk && ./6.out'
```

The result is `hello from nix9`. See [native development](docs/development.md#native-nix)
for package builds, environment updates and rollback.
The optional [Go bootstrap](docs/development.md#native-go) adds a Go toolchain
that rebuilds inside 9front and builds command packages with vendored dependencies.
For machine configuration, see [system generations](docs/development.md#system-configuration):
select packages, hostname, networking, generated files and certificate pins,
enable managed webfs, then switch or roll back.
The disk persists. Later, run only `run-vm` and source `/usr/local/pkg/nix9/activate` again.
Keep `result-vm` to retain the backing image. Run `fshalt` before stopping QEMU
with Ctrl-C. The host HTTP server can stop after installation.

## Documentation

- [Run the VM](docs/vm.md): persistent disks and package installation.
- [Develop packages](docs/development.md): cross-compilation, native builds and helpers.
- [Test coverage](docs/validation.md).
- [Status and limitations](docs/feasibility.md).
