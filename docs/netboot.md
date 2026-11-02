# PXE network boot

PXE lets an amd64 CPU fetch its loader, kernel and settings over TFTP, then mount
its authenticated [shared CWFS root](netroot.md). The local machine needs its
native NVRAM credentials, but no local kernel or OS filesystem.

The [netboot example](../examples/netboot/configuration.nix) extends the shared-root
installation with DHCP and TFTP on `files`. Its CPU declares:

```nix
{
  machines.build = {
    ether = "525400123462";
    boot = {
      provider = "files";
      root = "stable";
      pxe = {
        provider = "files";
        settings.console = 0;
      };
    };
  };
}
```

`boot.provider` supplies the CWFS root. `boot.pxe.provider` supplies TFTP;
both may refer to the same independently booted machine. DHCP can run on another
inventory machine or an existing server.
The inventory generates NDB `ether`, `bootf` and `tftp` entries for the CPU.
DHCP must advertise the boot file and TFTP server from those records.
Its static kernel network settings still match the inventory IP.

`boot.pxe.kernel` defaults to the pinned 9front 11952 amd64 kernel. Set it to
another compatible kernel file when needed. `settings` adds public `plan9.ini`
hardware parameters; generated identity, root, network and kernel settings are
reserved. The generated loader is `9bootpxe`, for BIOS/PXE firmware.

## Prepare and boot

Configure and boot the authentication and file servers. Follow the
[shared-root preparation](netroot.md#prepare-the-file-server) steps to publish
the root, prepare the CPU's private state and stage its initial system export.
Keep machine keys and NVRAM credentials in their private native locations.

On the TFTP provider, with CWFS mounted at `/n/site` and the built installation
in `$installation`:

```sh
boot=`{cat $installation/boot/build/path}
rc $boot/publish-pxe /lib/tftp
rc $boot/select-pxe /n/site
```

Publication copies public files into an immutable directory under `versions/`
and publishes the common loader. Selection writes `cfg/pxe/MAC`, which names the
versioned kernel and chosen CWFS root. It checks the published root and persistent
machine identity first. An existing configuration must belong to the same CPU.
Publication refuses a different common loader; update it separately when changing
loader versions.

Enable PXE boot in the CPU's firmware. The loader reads `/cfg/pxe/MAC` and fetches
the selected kernel. At the first console, import and select the staged Nix
system as described in [network-root boot](netroot.md#boot-and-select), then
reboot. There is no local `plan9.ini` to merge.

## Upgrade and roll back

Use the existing [deployment](deployment.md#shared-os-roots) commands:

```sh
nix9 deploy --prepare --from $next build
nix9 select-root --from $next build
nix9 status --from $next build
```

Preparation publishes the root on its CWFS provider and the boot files on its
TFTP provider. Both providers need administrative CPU access, or must be the
local coordinator. Selection checks every requested CPU and boot provider before
changing any selector. Other CPUs keep their selected configurations.

`status` reads the configuration actually served over TFTP through native
`ip/tftpfs`. It reports the running and next roots. Reboot the CPU to apply the
selection; TFTP needs no restart. Deploying and selecting an earlier retained
installation selects its earlier kernel and root. Nix system generations remain
separate from OS root selection.

Selection saves the previous configuration as `MAC.bak`; repeating an unchanged
selection preserves it. Native file replacement is not atomic; an interrupted
update may require restoring that backup. Published versions and writable CPU
state survive selection and rollback. Published copies remain until removed explicitly.

## TFTP and NDB options

`services.tftpd.enable` starts native `ip/tftpd` at boot. Its `directory` defaults
to `/lib/tftp`. The daemon runs as `none`, restricts requests to that public
directory and rejects parent traversal. Default directory permissions and
published file modes prevent client writes. Logs use `/sys/log/ipboot`.
`nix9 status --health` checks the UDP listener on port 69 and the directory.

For manually managed boot files, `services.ndb.hosts.NAME` and
`services.ndb.networks.NAME` accept `bootf` and `tftp`. `bootf` is the boot file
path; `tftp` accepts an NDB server name or an IP address. The structured
`records` and raw `extraConfig` options remain available for other native data.
