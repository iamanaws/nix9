# System services

See [service discovery](discovery.md) for generated NDB records and packaged cs/DNS.

These options belong inside [mkSystem](configuration.md) and are disabled by
default. See its [activation table](configuration.md#generations) for when
selection changes take effect.

## Ethernet networking

`networking.enable = true` configures `ether0` with DHCP, lease renewal, gateway
and DNS. `interface` selects another device such as `ether1`.
One primary Ethernet interface is supported. For static IPv4:

```nix
networking = {
  enable = true;
  useDHCP = false;
  address = "192.168.1.42";
  prefixLength = 24;
  defaultGateway = "192.168.1.1";
  nameservers = [ "192.168.1.1" ];
};
```

Static mode requires an address and a prefix length from 1 to 32; the gateway
is optional. DHCP rejects a static address or prefix. IPv4 octets are decimal
without leading zeros. Interface addresses and gateways exclude unspecified,
loopback and multicast ranges; DNS servers may use loopback. External IPv6
configuration is unavailable.

Networking configures both loopbacks, then starts `ndb/cs` and `ndb/dns -r`.
`ipconfig` records interface and DHCP data in `/net/ndb`, preserving
`/lib/ndb/local`. Explicit `nameservers` override DHCP DNS through `DNSSERVER`,
including after lease renewal. An empty list uses native NDB/DHCP settings.
The resolver clears inherited `DNSSERVER` and `DOTSERVER`.

Remove conflicting manual interface setup before enabling this option.
A preexisting `cs` or `dns` causes an error. Boot reports networking failures
on the console and continues. Disabling management restores native startup
on the next boot, which may still configure a network.

## Clock synchronization

`services.timesync.enable = true` runs native `aux/timesync` using the hardware
RTC as UTC. Set `rtcLocalTime = true` for an RTC in the existing 9front timezone.
For NTP instead:

```nix
services.timesync = {
  enable = true;
  source = "ntp";
  server = "time.example.org";
};
```

| Option | Values |
| --- | --- |
| `source` | `"rtc"` by default, or `"ntp"`. |
| `server` | Required for NTP; a DNS hostname or unicast IPv4 address. |
| `port` | NTP port, default 123; integer from 1 to 65535. |
| `rtcLocalTime` | Default false; true requires RTC. |
| `logging` | Default false; record corrections and failures in `/sys/log/timesync`. |

RTC rejects a server or nondefault port. Native NTP also updates a writable
RTC in UTC; it does not start an NTP listener.

Terminal startup uses `TIMESYNCARGS`; the CPU hook starts timesync directly.
Native process checks prevent a duplicate client. Remove manual timesync
invocations and conflicting `TIMESYNCARGS` assignments. On CPU servers, provide
networking in the managed hook or preserved local hook for the first NTP sample.
Networking started later may delay synchronization until a retry.

Disabling management restores native startup, normally a local-time RTC on
terminals and NTP on CPU servers. It does not stop synchronization.

## Logging

9front's `syslog(2)` writes to existing files in `/sys/log`. Prepare them with:

```nix
logging = {
  enable = true;
  files = {
    cs.mode = "0660";
    dns.mode = "0660";
    application = { }; # Defaults to 0640.
    nix9.mode = "0600";
  };
};
```

Logging always prepares `/sys/log/nix9`. Additional names may contain letters,
digits, dots, underscores or hyphens, start with a letter or digit, and have at
most 64 characters. Modes are four-digit octal strings with owner write permission;
the default is `0640`. Logs are append-only. Preparation preserves existing
contents, owners and groups; the startup user needs permission to change modes
and write records. Preparing `cs` or `dns` files does not enable their debug flags.

Preflight checks all declared file types before changing logs. Directories and
special files are rejected. Boot prepares logs before services start.
A later selection failure can leave created files or changed permissions, but
writes no successful selection event.

`/sys/log/nix9` records hostname, native timestamp, event and system store path.
Boot records precede managed services; switch and rollback records follow
successful selection. Record failures appear on the console without undoing
selection.

`services.timesync.logging = true` requires timesync to be enabled and also
enables log preparation and generation events. Its `timesync` log defaults to
`0660` for the stock image's `sys` group; override
`logging.files.timesync.mode` for other ownership.

Rollback restores permissions without losing history. Removing declarations
leaves files, data and last permissions in place. Selecting an unmanaged
generation writes one final event through the previous logger.
`logging.files` requires logging or timesync logging to be enabled.
Rotation and remote forwarding are not provided.

## Webfs

`services.webfs.enable = true` starts the bundled webfs after activating
certificate pins. It needs a working network, which can be configured manually.
HTTPS also needs a [trust policy](transport.md#https-trust).

Webfs mounts at `/mnt/nix9-webfs` and overlays `/mnt/web` in the session's
private namespace. Refreshing into a different system generation or bootstrap
starts a server with that TLS namespace; repeated activation reuses it.
Other sessions retain their servers and pins until refreshed. The shared
revocation file still applies to existing connections.

Activation rejects an occupied private mount, a manually replaced managed mount,
or a preexisting rc function named `webfs`. Rebuild preflight checks these without
starting a server or changing mounts. Managed activation supplies a `webfs`
function so bare startup in login profiles is idempotent. Calls with arguments
run the bundled program. Change the configuration rather than mounting over
managed webfs.

Disabling webfs or selecting a generation predating services removes the
session's managed overlay and reveals inherited manual mounts. Servers in other
namespaces keep running.

## Remote CPU login

Use 9front's native service and authentication configuration on an
[existing CPU server](configuration.md#boot-integration). Keep `tcp17019` in
the active service directory and provision credentials through NVRAM, factotum
and the authentication server. Keep credentials outside the Nix store.
See `auth(8)` and `factotum(4)` for provisioning.

Native `rcpu` authenticates through factotum and encrypts the connection with TLS.
From a 9front client with its key loaded:

```rc
rcpu -u USER -h HOST
rcpu -u USER -h HOST -c 'nix-build $nix9/hello'
```

The login hook activates Nix and the selected system before your profile.
Use the Nix store owner's account to build packages.
See [generation activation](configuration.md#generations) for switching,
rollback and existing sessions.

## CPU TCP services

On CPU servers, `services.listen` adds rc scripts to native `aux/listen`:

```nix
services.listen = {
  enable = true;
  tcp."17010" = ''
    cat /cfg/nix9/files/motd
  '';
};
```

`tcp` maps decimal ports from 1 to 65535, without leading zeros, to nonempty rc
scripts. Scripts require `enable = true` and run as `none`.
Connections use the booted generation's packages, files, certificate pins and
managed webfs. Arguments are service name, protocol and connection directory.
Standard input and output use the connection; standard error uses the console.

The native listener accepts connections on the machine's interfaces. It retains
manual services and per-service namespaces using native directory precedence:
`/cfg/$sysname/service`, `/cfg/default/service`, then `/rc/bin/service`.
The trusted authentication directory keeps its native behavior.

Selection rejects conflicts with a manual `tcpPORT` or `tcpPORT.namespace`.
Startup checks again; a late conflict reports an error and starts the original
service set. Other port collisions appear in native `/sys/log/listen`.

Existing and new connections keep using the booted generation until reboot.
The next CPU boot applies scripts and removes omitted ports. To disable, set
`enable = false` and remove `tcp` declarations. Older generations use the native
service set; terminal boots do not start these listeners.
Standalone daemon management is not provided.
