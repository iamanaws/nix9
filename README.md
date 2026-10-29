# nix9

Nix for Plan 9, tested on 9front. Build packages natively with `nix-build`,
evaluate expressions with `nix-instantiate`, or cross-compile on Linux.
Package environments and machine configurations support retained generations
and rollback.

The port is experimental. Native builds have no full sandbox, and the modern
`nix` CLI and flakes are unavailable in the guest.

## Quick start

Use x86_64 Linux with Nix flakes enabled. Your user and Nix builders need access
to `/dev/kvm`. Run host commands from the checkout.

The flake includes `nix9.cachix.org` as an optional binary cache to save build time.
A trusted cache can supply modified outputs, so only use it if you trust me.

On the host, prepare the VM and serve the bootstrap:

```sh
nix build .#vm-image -o result-vm
nix build .#native-bootstrap -o result-native-bootstrap
nix run .#setup-vm
nix develop -c python -m http.server 8000 --bind 127.0.0.1
```

Leave the server running. In another terminal, run `nix run .#run-vm`.
Press Enter at the boot arguments and user prompts, then wait for `term%`.
A missing-display message from `rio` is expected. In the guest:

```sh
ip/ipconfig ether /net/ether0
cd / && hget http://10.0.2.2:8000/result-native-bootstrap | tar x
. /usr/local/pkg/nix9/activate
nix-build $nix9/packages -A fortune
result=`{cat /usr/local/nix/state/gcroots/result}
$result/bin/fortune
```

Run `fshalt` before stopping QEMU with Ctrl-C. Keep `result-vm` to retain the
disk's backing image. See [VM details](docs/vm.md) for later boots, other disks
and a C development example.

## Documentation

| Guide | Contents |
| --- | --- |
| [VM details](docs/vm.md) | Native development, persistent disks and package archives. |
| [Native Nix](docs/native.md) | Builds, environments, updates, releases and store maintenance. |
| [Package development](docs/development.md) | Toolchains, recipes, development shells and native Go. |
| [System configuration](docs/configuration.md) | Machine settings, switching, rollback and boot hooks. |
| [Installation inventory](docs/installation.md) | Machines, shared discovery, provider references and system closures. |
| [Services](docs/services.md) | Ethernet, clock synchronization, logging, webfs and remote CPU access. |
| [Service discovery](docs/discovery.md) | NDB records, service locations and native cs/DNS. |
| [Downloads and caches](docs/transport.md) | HTTPS trust, source fetches, closure transfers and signed caches. |
| [Tests](docs/validation.md) | Test commands, coverage and benchmarks. |
| [Limitations](docs/feasibility.md) | Port constraints and missing features. |
| [Upstream patches](docs/upstream.md) | Patch ownership and removal criteria. |
