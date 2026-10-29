# Service discovery

`services.ndb` generates an NDB database and selects packaged native NDB tools.
It describes service locations; it does not provision authentication keys,
accounts or file exports. Inside a `mkSystem` configuration:

```nix
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
```

Host names are lowercase labels. Each host has one IPv4 address and may also
declare `dom`, `ether`, `authdom`, `dns` and `ntp`. Ethernet addresses use twelve
lowercase hexadecimal digits. `auth`, `fs` and `cpu` refer to declared host names.
Networks require aligned IPv4 addresses and a prefix length from 0 to 32. Their
defaults apply through native NDB subnet lookup. `dns` and `ntp` are lists.

Declarations retain NDB tuple and line grouping. Duplicate host addresses,
invalid networks and missing service references fail before selection.

## Existing databases

Declared entries are searched first, followed by the ordered `include` list.
Its default is:

```nix
services.ndb.include = [
  "/lib/ndb/common"
  "/cfg/nix9/ndb-original"
];
```

Activation preserves the original local database through a separate file bind
before replacing `/lib/ndb/local` in the namespace. The original remains available
at `/cfg/nix9/ndb-original`. Add other databases to `include` as needed. Included
files must be readable. Structured declarations currently cover IPv4; existing
files can supply other NDB records.

## Startup and queries

NDB files and tools follow session activation. Running `cs` and DNS retain their
booted generation until reboot. With managed networking enabled, NDB is available
before IP configuration, then the packaged services start. Native startup also
uses these services when it performs network setup itself.

`services.ndb.dns.enable = false` suppresses DNS startup, including the native
fallback. `dns.resolver` defaults to true. Disabling `services.ndb` restores the
native database and startup on the next boot.

Host `dom` entries are DNS hints. Upstream DNS answers can take precedence;
authoritative zones require manual NDB records and native DNS server setup.

```rc
ndb/query sys cpu1 ip
ndb/ipquery ip 10.0.0.20 auth fs cpu authdom
ndb/csquery /net/cs tcp!cpu1!17019
```
