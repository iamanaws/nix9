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

## Install a package

On the host, build and serve the Lua archive:

```sh
nix build .#lua-package -o result-package
nix develop -c python -m http.server 8000 --bind 127.0.0.1
```

In the guest, with networking configured:

```sh
hget -o /tmp/package.tar http://10.0.2.2:8000/result-package
cd / && tar xf /tmp/package.tar
path=(/usr/local/pkg/lua-5.4.8/bin $path)
lua -e 'print(_VERSION)'
```

Packages use `/usr/local/pkg/NAME-VERSION`, with `bin` and `share` directories. Lua finds
modules in its `share/lua/5.4` directory. The shell path change lasts for this session.
