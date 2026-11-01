# DHCP

`services.dhcpd` runs native `ip/dhcpd`. Reservations come from NDB hosts with
an `ip` and `ether` on the requesting network. Network records supply defaults:

```nix
{
  networking = {
    enable = true;
    interfaces.ether0 = {
      useDHCP = false;
      address = "172.23.0.10";
      prefixLength = 24;
    };
  };
  services = {
    ndb = {
      hosts = {
        files.ip = "172.23.0.11";
        auth.ip = "172.23.0.12";
        terminal = {
          ip = "172.23.0.20";
          ether = "525400123456";
        };
      };
      networks.lab = {
        address = "172.23.0.0";
        prefixLength = 24;
        ipgw = "172.23.0.1";
        dns = [ "172.23.0.10" ];
        dnsdomain = [ "lab.example.test" ];
        fs = "files"; # Or "172.23.0.11".
        auth = "172.23.0.12"; # Or "auth".
      };
    };
    dhcpd = {
      enable = true;
      pools = [ { start = "172.23.0.100"; count = 20; } ];
    };
  };
}
```

Both `fs` and `auth` accept NDB names or literal IP addresses. The DHCP server
resolves names through NDB and sends the resulting addresses to clients.

This pool includes `.100` through `.119`. Omit `pools` to serve only reservations.
Pools cannot overlap each other, known NDB hosts, configured static addresses or
declared network/broadcast addresses. Keep addresses declared in raw NDB or
external files out of pools yourself.

Enabling DHCP also enables managed NDB. Host values override subnet and parent
network defaults, as described in [service discovery](discovery.md). `dns`
advertises a DNS server; enable [DNS serving](discovery.md#serving-dns) separately
if this machine provides it.

The daemon listens on UDP port 67 across `/net`, serving matching reservations
and pools on directly connected or relayed networks. It disables BOOTP replies.
Give the server a stable address and configure client interfaces with
`useDHCP = true`.

`minimumLease` defaults to 900 seconds for dynamic clients without a requested
duration; native DHCP honors client requests for other durations. `staticLease`
defaults to 1800 seconds and uses at least `minimumLease` for reservations.

Dynamic leases live in writable `/lib/ndb/dhcp`, outside the store. Selection,
rollback and disabling the service preserve them. Running DHCP keeps its booted
NDB and pools until reboot.

```sh
ip/dhcpleases
nix9 status --health
```

Logs use `/sys/log/ipboot`. Health checks verify the UDP listener and a writable
lease directory. The [lab example](../examples/lab/configuration.nix) extends the DNS
installation with a reserved terminal and a pool for other clients. Build it
through `examples/lab/default.nix`, and replace the example terminal's MAC with
its actual Ethernet address.
