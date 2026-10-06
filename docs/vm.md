# Run the VM

Start with the [native Nix quick start](../README.md#quick-start).
The flake pins the base image from
[9front-in-a-box](https://github.com/majiru/9front-in-a-box).
The launcher uses two CPUs, 2 GiB RAM and a serial console.

## Persistent disk

Setup creates `9front.hjfs.amd64.qcow2` in the current directory. It refuses to
replace an existing file. Keep `result-vm` while using that disk so Nix garbage
collection retains its backing image.

Both launchers accept a disk filename:

```sh
nix run .#setup-vm -- experiment.qcow2
nix run .#run-vm -- experiment.qcow2
```

The smoke tests use temporary snapshots and discard their changes.

## Install packages

On the host, build and serve the default environment:

```sh
nix build .#guest-environment -o result-package
nix develop -c python -m http.server 8000 --bind 127.0.0.1
```

In the guest, run `ip/ipconfig ether /net/ether0` if networking is not configured,
then install and activate the environment:

```sh
hget -o /tmp/package.tar http://10.0.2.2:8000/result-package
cd / && tar xf /tmp/package.tar
. /usr/local/env/default/activate
lua -e 'print(_VERSION)'
```

The environment bundles Lua and the checksum tool under `/usr/local/pkg`.
The `activate` script sets command paths for this session and APE subprocesses.
Individual package archives also have an `activate` file.
