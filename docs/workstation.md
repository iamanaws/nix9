# Graphical sessions

Declare a graphical workspace in a machine configuration:

```nix
session = {
  enable = true;
  acme = {
    directory = "/n/projects/hello";
    files = [ "hello.c" "default.nix" ];
  };
  windows = [ { directory = "/n/projects/hello"; } ];
};
```

Select the system, then run `nix9-session` from a terminal with graphics and
mouse devices. It activates the selected generation, including shared mounts
and builders, then starts a private plumber and Rio with an Acme window and
the declared shell windows. Rio, Acme, plumbing tools and DejaVu bitmap fonts
are built from the pinned 9front sources.

For the test VM, use `nix run .#run-vm -- --graphics`. At the serial prompt,
prepare the display once per boot before starting the session:

```sh
monitor=vesa vgasize=1024x768x32 screenrc
nix9-session
```

Use the QEMU window for mouse and keyboard input once Rio starts. See
[VM details](vm.md) for installation and disk options.

## Settings and lifecycle

| Option | Default and behavior |
| --- | --- |
| `session.font` | Packaged DejaVu 12. Used by Rio and Acme. A font in another package retains that dependency. |
| `session.scroll` | `true`, enabling scrolling in new Rio windows. |
| `session.windows` | One interactive rc shell. Each entry accepts `command`, `directory` and `rectangle`. Commands are argument lists; directories default to the user's home. Rectangles are `[ left top right bottom ]` in pixels, or `null` for native placement. |
| `session.acme` | Starts Acme by default. Supports `enable`, `directory`, `files`, `rectangle`, `columns`, `tabStop` and `fixedFont`. Files are relative to the editor's directory; columns default to 2 and tabs to 4. |
| `session.plumbingRules` | Native rules routing existing files, directories and file addresses such as `hello.c:7` to an open editor. Supply your own rules for other destinations. |

Settings apply when starting the next session. Selection, rollback and sourcing
`/usr/local/pkg/nix9/system` leave running windows alone. Exit Rio before starting
another managed session; starting one inside an existing managed session fails.
The session's plumber stops when Rio exits; an existing plumber remains running.
Save editor buffers before exiting.

The launcher is explicit. To use it at login, replace the `plumber` and `rio`
calls in your native `$home/lib/profile` with `nix9-session`. Machine selection
does not edit that file. Display hardware and boot configuration remain native.

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

Start `nix9-session` on the terminal. Acme opens the shared source and recipe.
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
