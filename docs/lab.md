# Run a development lab

The lab provisions the [four-machine development installation](install.md) on a
private virtual Ethernet network: authentication, CWFS storage and two CPUs.
It runs on x86_64 Linux with Nix and `/dev/kvm`, using 8 GiB RAM while running.
Run from the checkout:

```sh
nix run .#lab
```

The first run installs Nix, the C toolchain and server packages, creates lab
credentials and storage, publishes the shared OS root and selects each CPU's
initial system. Preparation can take tens of minutes. Guest output is saved in
`nix9-lab/control.log`.
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

`build` sends Nix compilation to `batch`; `nix-build` returns the results to
`build`'s shared store. Both CPUs see the same project and homes on CWFS, with
separate Nix stores and generations. Use `batch` for a direct CPU login, or
`-u bob` for Bob.
Use `exit` to return to the auth console. Ctrl-C interrupts a guest command;
Ctrl-] detaches the host terminal.
Other consoles are available with `console files`, `console build` and
`console batch`.

To see where the sample program was compiled:

```sh
nix-build default.nix
roots=`{nix-store --roots-dir}
result=`{cat $roots/result}
cat $result/builder
```

It reports `batch`. Its daemon accepts the lab's dedicated `builder` identity;
`build` loads that account's client key from `/adm/builder.keys`. Alice and Bob
use ordinary daemon access and separate profiles. Cached outputs remain usable
on `build` when the builder is unavailable; a new build requires `batch`.

Press Ctrl-C in the launcher's terminal to stop the lab. It halts the CPUs
before the file and authentication servers. Run the same command to resume;
projects, credentials, profiles and selected generations remain on disk.
If a CPU VM exits, the other machines keep running. Stop and resume the lab to
bring that CPU back.

## State and configuration

Choose another state directory with `nix run .#lab -- ./my-lab`. Pass that
directory after the machine name when opening a console. `nix run .#lab -- status`
shows the default lab's state and addresses. Each lab uses its own private
network; the running machines have no connection to the host or Internet.

The state directory contains private credentials and writable disks and is
ignored by Git. Keep it at the same path. Nix GC roots retain the backing image
and bootstrap. The CWFS devices are sparse files with an 11 GiB combined capacity;
disk usage grows as you add data. Existing disks are never replaced. If initial
preparation fails, keep `control.log` for diagnosis and use a new directory for a
fresh attempt.

The lab uses the [development example's starter](../examples/development/default.nix),
also used by the [manual installation guide](install.md).
The initial site configuration is saved as `configuration.nix` on the host and
`/cfg/nix9-lab/default.nix` on the auth and file servers. Edit the guest copy on
`files` and follow [deployment](deployment.md) for changes. The launcher preserves
the selected systems on later starts.

## Update one CPU

On the `files` console, edit `/cfg/nix9-lab/default.nix`. For example, add this
module to its existing `imports` list:

```nix
{
  machines.build.configuration.files.message = "Updated CPU configuration\n";
}
```

Then deploy from that directory:

```sh
cd /cfg/nix9-lab
nix9 deploy build
nix9 status --health build
```

Status reports the selected and booted systems separately. At the `build`
console, run `fshalt -r`. The launcher restores that console after boot and
reports when the CPU's health checks pass. Existing console connections stay
open; `console build` also reconnects normally. `batch`, auth and storage keep
running. `nix run .#lab -- status` shows each machine's readiness during the reboot.

To undo the selection, run at the `build` console:

```sh
nix9-rebuild rollback
fshalt -r
```

Rollback preserves projects and user profiles. Update the source configuration
before deploying again. For auth or file-server changes, stop and resume the
whole lab so the CPUs halt before their providers.

For an unavailable remote builder, use the [local compilation recovery](builders.md#recover-while-a-builder-is-unavailable)
workflow. It changes the submitting CPU's build settings without rebooting it.

After stopping the lab, removing its state directory discards the installation
and releases its Nix GC roots.

To run the setup, development and restart integration test:

```sh
nix run .#lab-tests -- ./lab-results
```
