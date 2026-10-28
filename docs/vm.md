# Run the VM

The flake pins a 9front image from
[9front-in-a-box](https://github.com/majiru/9front-in-a-box).
The launcher uses two CPUs, 2 GiB RAM and a serial console.

Follow the [README quick start](../README.md#quick-start) to install native Nix.

## Native development

The archive includes Nix, a pinned package set and a signed development-tool
cache. Without cached outputs, preparing it builds native packages in a VM.

Try the included C project:

```rc
mkdir /tmp/hello
cp $nix9/hello/* /tmp/hello
cd /tmp/hello
nix-shell default.nix --run 'mk && ./6.out'
```

It prints `hello from nix9`. Continue with [native Nix](native.md) or
[system configuration](configuration.md).

## Persistent disks

Setup creates `9front.hjfs.amd64.qcow2` and refuses to replace an existing file.
Keep `result-vm` so Nix GC retains the backing image. Both launchers accept
another disk filename:

```sh
nix run .#setup-vm -- experiment.qcow2
nix run .#run-vm -- experiment.qcow2
```

For 4 GiB RAM, launch QEMU directly instead of `run-vm`:

```sh
nix develop -c qemu-system-x86_64 -enable-kvm -m 4G -smp 2 \
  -display none -monitor none -serial stdio \
  -drive file=9front.hjfs.amd64.qcow2,format=qcow2,if=virtio -nic user
```

Run `fshalt` before stopping QEMU with Ctrl-C. The HTTP server can stop after
installation. On later boots, run only `run-vm` and source
`/usr/local/pkg/nix9/activate` in the guest. Tests use disposable snapshots.

## Package archives

To install cross-built tools without native Nix, build and serve an archive:

```sh
nix build .#guest-environment -o result-package
nix develop -c python -m http.server 8000 --bind 127.0.0.1
```

Configure guest networking if needed, then extract and activate:

```rc
ip/ipconfig ether /net/ether0
cd / && hget http://10.0.2.2:8000/result-package | tar x
. /usr/local/env/default/activate
lua -e 'print(_VERSION)'
```

This environment bundles Lua and the checksum tool. Activation sets rc and APE
command paths for the session. Individual package archives also have an
`activate` file.

For native C tools, substitute `guest-development` on the host, then run:

```rc
. /usr/local/env/development/activate
6c -o main.6 main.c
6l -o main main.6
./main
```

Use `pcc -o program source.c` for APE POSIX C. These wrappers use rebuilt tools,
headers and runtimes; `pcc` supplies APE's standard paths in a private namespace.
