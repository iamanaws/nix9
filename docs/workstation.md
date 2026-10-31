# Rio, Acme and plumbing

Configure native programs in a machine module:

```nix
{
  services.plumber.enable = true;
  programs = {
    rio = {
      enable = true;
      windows = [ { directory = "/n/projects/hello"; } ];
    };
    acme = {
      enable = true;
      start = true;
      directory = "/n/projects/hello";
      files = [ "hello.c" "default.nix" ];
    };
  };
}
```

Nix installs the programs and generates their arguments, Rio startup commands
and plumbing rules. `programs.acme.start` includes an Acme window in Rio's
startup; `enable` alone installs and configures Acme for manual use.

## Native startup

After selection, activate the system and source the generated defaults. Launch
ordinary programs:

```sh
. /usr/local/pkg/nix9/system
. $nix9System/programs/profile
plumber $plumberargs
rio $rioargs
```

In `$home/lib/profile`, source `programs/profile` after native font defaults
and before the terminal's `plumber` and `rio` calls. Pass the corresponding
argument lists to those calls. Selection does not edit the user's profile or
start programs.

The fragment sets `font`, `tabstop`, `rioargs`, `acmeargs` and `plumberargs`,
and exposes Nix commands in `/bin` for programs such as Acme. It launches nothing.
For manual editor startup, run `acme $acmeargs`. Native commands and explicit
arguments remain available for custom workflows.

Rio's arguments include `-i` with the generated `riostart` script; bare `rio`
does not run that script. Plumber uses `-p` with generated rules. Plumber has its
own lifetime and remains running when Rio exits. Existing windows and plumbers
keep their configuration until explicitly restarted. Refreshing a namespace
or selecting another generation does not restart them.

For the test VM, use `nix run .#run-vm -- --graphics` and prepare the display
before starting Rio:

```sh
monitor=vesa vgasize=1024x768x32 screenrc
```

Use the QEMU window for keyboard and mouse input. Display hardware and boot
configuration remain native; see [VM details](vm.md).

## Settings

| Option | Default and behavior |
| --- | --- |
| `programs.rio.font` | Packaged DejaVu 12, also used by the editor. Package references retain their font dependencies. |
| `programs.rio.scroll` | `true`, enabling scrolling in new windows. |
| `programs.rio.windows` | One interactive rc shell. Entries accept `command`, `directory` and `rectangle`. Commands are argument lists; directories default to home. Rectangles are `[ left top right bottom ]`, or `null` for native placement. |
| `programs.acme` | `enable` installs Acme; `start` opens it from `riostart`. Also accepts `directory`, `files`, `rectangle`, `columns`, `tabStop` and `fixedFont`. Columns default to 2 and tabs to 4. |
| `services.plumber.rules` | Native rules routing files, directories and addresses such as `hello.c:7` to an open editor. |

## Shared development installation

The [workstation example](../examples/workstation/configuration.nix) has four
machines: authentication, shared project files, a build CPU and a graphical
terminal. Each has its own writable Nix store.

Copy and build it in an activated Nix session:

```sh
mkdir -p /usr/glenda/workstation
cp $nix9/packages/examples/workstation/*.nix /usr/glenda/workstation/
cd /usr/glenda/workstation
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/workstation
```

Provision [authentication](access.md), networking and server keys, then
[deploy](deployment.md) the machine systems. Prepare `/cfg/HOST/service` on each
server before selection so managed listeners use that directory; see
[TCP services](services.md#cpu-tcp-services). The authentication database needs
`files`, `build` and `glenda`; the file server loads `/adm/files.keys`, the CPU
loads `/adm/cpu.keys`, and the terminal's factotum needs Glenda's client key
for `nix9.workstation`. Keep credentials outside expressions and the store.

On the file server, copy the sample project into the declared export:

```sh
mkdir -p /usr/glenda/projects/hello
cp $nix9/packages/examples/workstation/project/* /usr/glenda/projects/hello/
```

Use the native startup commands above on the terminal. Acme opens the shared
source and recipe.
Edit and `Put` the source, then run `nix-build default.nix` in the shell window.
Nix sends the source snapshot to the CPU and returns the compiled output.
Run it locally:

```sh
result=`{cat /usr/local/nix/state/gcroots/result}
$result/bin/hello
```

Project edits live on the file server; build outputs live in the terminal's
store. [Storage](storage.md) and [backups](backups.md) describe persistent CWFS
workspaces and independent archives.
