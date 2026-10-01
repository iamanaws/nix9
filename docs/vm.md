# Run the VM

On x86_64 Linux with KVM and Nix flakes enabled:

```sh
nix build .#vm-image -o result-vm
nix run .#setup-vm
nix run .#run-vm
```

Your user and Nix builders need access to `/dev/kvm`.
The flake pins the image from
[9front-in-a-box](https://github.com/majiru/9front-in-a-box).

## Console

Press Enter at the boot arguments and user prompts. If `rio` reports a missing
display, wait for the `term%` serial shell.

Inside the guest, configure networking with:

```sh
ip/ipconfig ether /net/ether0
```

Run `fshalt` before stopping QEMU with Ctrl-C.

## Persistent disk

Setup creates `9front.hjfs.amd64.qcow2` in the current directory and refuses to
replace an existing file. Keep `result-vm` while using that disk so Nix garbage
collection retains its backing image.

Both launchers accept a disk filename:

```sh
nix run .#setup-vm -- experiment.qcow2
nix run .#run-vm -- experiment.qcow2
```

The smoke tests use temporary snapshots and discard their changes.
