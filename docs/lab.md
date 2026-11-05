# Run a development lab

The lab provisions the [four-machine development installation](install.md) on a
private virtual Ethernet network: authentication, CWFS storage and two CPUs.
It runs on x86_64 Linux with Nix and `/dev/kvm`, using 8 GiB RAM while running.
Run from the checkout:

```sh
nix run .#lab
```

The first run installs Nix, the C toolchain and server packages, creates lab
credentials and storage,
publishes the shared OS root and selects each CPU's initial system. Preparation
takes several minutes. Guest output is saved in `nix9-lab/control.log`.
Subsequent runs boot the existing disks.

Leave the launcher running. In another terminal, open the auth server's console:

```sh
nix run .#lab -- console auth
```

Press Enter for a prompt. Alice, Bob and Glenda's lab keys are already loaded in
factotum. Use an ordinary CPU login:

```sh
rcpu -u alice -h build
cd /n/projects/hello
nix-build environment.nix
nix-shell --run '6c hello.c && 6l hello.6 && ./6.out'
```

Use `batch` for the second CPU, or `-u bob` for Bob. Both CPUs see the same
project and homes on CWFS; each has its own shared Nix store and generations.
Use `exit` to return to the auth console. Ctrl-C interrupts a guest command;
Ctrl-] detaches the host terminal.
Other consoles are available with `console files`, `console build` and
`console batch`.

Press Ctrl-C in the launcher's terminal to stop the lab. It halts the CPUs
before the file and authentication servers. Run the same command to resume;
projects, credentials, profiles and selected generations remain on disk.

## State and configuration

Choose another state directory with `nix run .#lab -- ./my-lab`. Pass that
directory after the machine name when opening a console. `nix run .#lab -- status`
shows the default lab's state and addresses. Each lab uses its own private
network; the running machines have no connection to the host or Internet.

The state directory contains private credentials and writable disks and is
ignored by Git. Keep it at the same path. Nix GC roots retain the backing image
and bootstrap. The CWFS
devices are sparse files with an 11 GiB combined capacity; disk usage grows as
you add data. Existing disks are never replaced. If initial preparation fails,
keep `control.log` for diagnosis and use a new directory for a fresh attempt.

The initial site configuration is saved as `configuration.nix` on the host and
`/cfg/nix9-lab/default.nix` on the auth and file servers. Edit the guest copy on
`files` and follow [deployment](deployment.md) for changes. The launcher preserves
the selected systems on later starts.

After stopping the lab, removing its state directory discards the installation
and releases its Nix GC roots.

To run the setup, development and restart integration test:

```sh
nix run .#lab-tests -- ./lab-results
```
