# Network server

A Plan 9 network stack is a file tree. Export it from a machine connected to
a lab network, then use it from a terminal or CPU session. The client chooses
the network by path, without changing its own interfaces or routes.

The bundled [example](../examples/network-server/configuration.nix) has five machines:

| Machine | Purpose |
| --- | --- |
| `auth` | Authentication and delegation for the CPU server. |
| `labnet` | DHCP on management interface `ether0`, static `172.23.0.10/24` on lab interface `ether1`. Exports `/net`. |
| `device` | A test server at `172.23.0.20`, connected only to the lab network. Replies to `status` on TCP port 17080. |
| `cpu` | Runs commands with the imported network available at `/n/labnet`. |
| `terminal` | Starts CPU sessions and can also use the imported network directly. |

## Prepare the installation

With native Nix active, copy and build the example:

```sh
cp -r $nix9/packages/examples/network-server /usr/glenda/network-lab
cd /usr/glenda/network-lab
nix-build default.nix -A build --out-link /usr/local/nix/state/gcroots/network-lab
```

Edit the addresses for the site before selecting systems. The management
addresses are `10.0.2.100` through `10.0.2.103`; provide DHCP reservations or
use static configuration. Connect only `labnet`'s second adapter and `device`
to the lab network. See [interface configuration](services.md#ethernet-networking).

Provision accounts and [authentication keys](access.md) through native tools.
The auth server needs the `cpu`, `labnet` and `glenda` identities. The CPU's
runtime key file `/adm/cpu.keys` contains its server and delegation keys;
`/adm/labnet.keys` contains the provider's server key. The terminal needs
Glenda's client key in factotum. All use authentication domain `nix9.lab`.
Keys stay outside the configuration and store.

Select each machine's system through the [installation workflow](installation.md).
The server machines need native CPU-mode boot; only `cpu` enables remote CPU
login in this example. Reboot to start networking and listeners.

## Use the provider's network

The export uses the existing sharing options:

```nix
services.exports.lab = {
  path = "/net";
  allowedUsers = [ "glenda" ];
  readOnly = false;
  keyFile = "/adm/labnet.keys";
  keyPattern = "dom=nix9.lab user=labnet";
};
```

Network connections require writes to `clone`, `ctl` and `data` files, so the
export must be writable. It exposes the provider's `/net` stack, including
both networks and the controls permitted by native permissions.

The inventory connects the terminal and CPU's `lab` mounts to this export.
In the terminal:

```sh
. /usr/local/pkg/nix9/system
echo status | dial -e /n/labnet/tcp!172.23.0.20!17080
rcpu -h cpu -c 'echo status | dial -e /n/labnet/tcp!172.23.0.20!17080'
```

The example installs `pkgs.dial`, which provides the native dial tool as `dial`.
Both commands print `lab-device-ready`. The second command runs on the CPU,
using delegated authentication to mount the network as the logged-in user.
Its connection to the device originates from `labnet`. Replace the sample
device with a real lab service and use its protocol over the imported TCP tree.

Network changes and export policy apply at provider boot. Provider reboots
close existing connections; new sessions reconnect. The required mount prevents
CPU login commands from running while the provider is unavailable. CPU services
can still boot independently. See [sharing](sharing.md#changes-and-failures)
for refresh and conflict behavior.
