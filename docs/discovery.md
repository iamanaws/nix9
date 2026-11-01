# Service discovery

`services.ndb` generates an NDB database and selects packaged native NDB tools.
It describes service locations; it does not provision authentication keys,
accounts or file exports. Inside a `mkSystem` configuration:

```nix
{
  services.ndb = {
    enable = true;
    hosts = {
      fs1.ip = "10.0.0.2";
      cpu1 = { ip = "10.0.0.3"; dom = "cpu1.example.net"; auth = "fs1"; fs = "fs1"; };
    };
    networks.lab = {
      address = "10.0.0.0";
      prefixLength = 24;
      auth = "fs1";
      fs = "fs1";
      cpu = "cpu1";
      authdom = "lab";
    };
  };
}
```

Host names and `aliases` are lowercase labels. Each host has a primary IPv4
address and may declare `dom`, `ether`, `authdom`, `ipgw`, `dns`, `dnsdomain`
and `ntp`. `auth`, `fs` and `cpu` accept native server names or addresses,
including providers outside the installation. Ethernet addresses use twelve
lowercase hexadecimal digits.
Networks require aligned IPv4 addresses and a prefix length from 0 to 32. Their
defaults apply through native NDB subnet lookup: host values override the most
specific subnet, followed by its parent networks. `dns`, `dnsdomain` and `ntp`
are ordered lists.

For a machine on several networks, associate each extra IP with its own MAC
address and gateway:

```nix
{
  services.ndb.hosts.cpu1 = {
    ip = "10.0.0.3";
    aliases = [ "compute" ];
    extraAddresses = [
      { ip = "172.23.0.10"; ether = "525400123457"; ipgw = "172.23.0.1"; }
    ];
  };
}
```

Each address gets its own NDB line. Duplicate addresses or names and invalid
networks fail before selection. NDB advertises addresses; configure interfaces
separately through [networking](services.md#ethernet-networking).

## Other records

`records` expresses other NDB data as Nix attributes, including authentication
domains, named ports, DNS zones, boot parameters and IPv6:

```nix
{
  services.ndb.records = [
    { authdom = "lab"; auth = "10.0.0.2"; }
    { tcp = "artifacts"; port = 17050; }
    [
      { dom = "example.net"; soa = ""; }
      { mx = "mail1.example.net"; pref = 10; }
      { mx = "mail2.example.net"; pref = 20; }
    ]
    { sys = "build-cache"; ip = "2001:db8::10"; }
  ];
}
```

An attribute set is one record. A list of attribute sets is one record spanning
several lines, so each mail server above keeps its own preference. Values accept
strings or integers; lists repeat an attribute, such as `dns = [ "10.0.0.2"
"10.0.0.3" ];`. An empty string represents a flag such as `soa=`.

Modules append records in order; `lib.mkBefore` and `lib.mkAfter` control their
order. Hosts and networks come first, then `records`, then raw `extraConfig`.
Use `extraConfig = builtins.readFile ./local.ndb;` to import native text when
needed. Structured values reject double quotes and newlines. Interface
configuration remains IPv4.

## Installation records

An installation's `ndb` module extends discovery for every machine:

```nix
{
  ndb = {
    hosts.cpu.aliases = [ "compute" ];
    networks.lab = {
      address = "172.23.0.0";
      prefixLength = 24;
      fs = "files-lab.example.net";
    };
  };
}
```

The inventory owns machine identities and primary addresses. Other host fields
and additional hosts can be declared here or in a machine's
`configuration.services.ndb`. Installation `defaults` become the fallback
`networks.default` entry at `0.0.0.0/0`, so subnets can override them.

The [discovery example](../examples/discovery/configuration.nix) combines two
networks, a CPU with two interfaces, aliases, host and subnet overrides, external
providers and structured NDB records. Select its systems through the
usual [installation workflow](installation.md). Its external provider addresses
are examples to replace for the site. CPU login still needs native accounts and
[keys](access.md).

## Existing databases

Declared entries are searched first, followed by the ordered `include` list.
Its default is:

```nix
{
  services.ndb.include = [
    "/lib/ndb/common"
    "/cfg/nix9/ndb-original"
  ];
}
```

Activation preserves the original local database through a separate file bind
before replacing `/lib/ndb/local` in the namespace. The original remains available
at `/cfg/nix9/ndb-original`. Add other databases to `include` as needed. Included
files must be readable regular files. To manage an included database with Nix:

```nix
{
  files."site.ndb" = builtins.readFile ./site.ndb;
  services.ndb.include = [ "/lib/ndb/common" "/cfg/nix9/files/site.ndb" ];
}
```

Includes under `/cfg/nix9/files/` use the declared contents from that generation.
They become immutable store files, available before networking starts and
retained through garbage collection and rollback. Other include paths refer to
runtime files. The include list supports normal module ordering.
Native NDB reads this list from the root database; `database=` entries inside
included files are not followed recursively.

## Startup and queries

NDB files and tools follow session activation. Running `cs` and DNS retain their
booted generation until reboot. With managed networking enabled, NDB is available
before IP configuration, then the packaged services start. Native startup also
uses these services when it performs network setup itself.

`services.ndb.dns.enable = false` suppresses DNS startup, including the native
fallback. `dns.resolver` defaults to true. Disabling `services.ndb` restores the
native database and startup on the next boot.

Host `dom` entries are DNS hints. Upstream DNS answers can take precedence.
Serving DNS, DHCP or PXE to other machines requires native service setup in
addition to the database records.

```sh
ndb/query sys cpu1 ip
ndb/ipquery ip 10.0.0.20 auth fs cpu authdom
ndb/csquery /net/cs tcp!cpu1!17019
```
