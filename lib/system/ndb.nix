{ configuration, package }:
let
  error = message: throw "mkSystem: services.ndb.${message}";
  label =
    value:
    builtins.isString value
    && builtins.stringLength value <= 63
    && builtins.match "[a-z0-9]([a-z0-9-]*[a-z0-9])?" value != null;
  split = value: builtins.filter builtins.isString (builtins.split "\\." value);
  validIP =
    value:
    builtins.isString value
    && builtins.length (split value) == 4
    && builtins.all (
      part: builtins.match "(0|[1-9][0-9]{0,2})" part != null && builtins.fromJSON part <= 255
    ) (split value);
  safe = value: builtins.isString value && value != "" && builtins.match "[^\"\r\n]+" value != null;
  quoted = value: "\"${value}\"";
  pair = name: value: "${name}=${quoted value}";
  optional = name: value: if value == null then [ ] else [ (pair name value) ];
  values = name: items: map (pair name) items;
  line = pairs: builtins.concatStringsSep " " pairs;
  power = count: if count == 0 then 1 else 2 * power (count - 1);
  maskParts =
    prefix:
    builtins.genList (
      index:
      let
        bits = prefix - index * 8;
      in
      if bits >= 8 then
        255
      else if bits <= 0 then
        0
      else
        256 - power (8 - bits)
    ) 4;
in
(
  {
    enable ? false,
    hosts ? { },
    networks ? { },
    records ? [ ],
    extraConfig ? "",
    include ? [
      "/lib/ndb/common"
      "/cfg/nix9/ndb-original"
    ],
    dns ? { },
  }:
  let
    recordText = import ./ndb-records.nix records;
    host =
      {
        ip,
        aliases ? [ ],
        extraAddresses ? [ ],
        dom ? null,
        ether ? null,
        auth ? null,
        fs ? null,
        cpu ? null,
        authdom ? null,
        dns ? [ ],
        ntp ? [ ],
        ipgw ? null,
        dnsdomain ? [ ],
      }:
      {
        inherit
          ip
          aliases
          extraAddresses
          dom
          ether
          auth
          fs
          cpu
          authdom
          dns
          ntp
          ipgw
          dnsdomain
          ;
      };
    network =
      {
        address,
        prefixLength,
        auth ? null,
        fs ? null,
        cpu ? null,
        authdom ? null,
        dns ? [ ],
        ntp ? [ ],
        ipgw ? null,
        dnsdomain ? [ ],
      }:
      {
        inherit
          address
          prefixLength
          auth
          fs
          cpu
          authdom
          dns
          ntp
          ipgw
          dnsdomain
          ;
      };
    hostNames = builtins.attrNames hosts;
    networkNames = builtins.attrNames networks;
    hostData = builtins.mapAttrs (_: host) hosts;
    networkData = builtins.mapAttrs (_: network) networks;
    allRecords = builtins.attrValues hostData ++ builtins.attrValues networkData;
    defaults =
      record:
      optional "auth" record.auth
      ++ optional "fs" record.fs
      ++ optional "cpu" record.cpu
      ++ optional "authdom" record.authdom
      ++ values "dns" record.dns
      ++ values "dnsdomain" record.dnsdomain
      ++ values "ntp" record.ntp;
    hostText =
      name:
      let
        record = hostData.${name};
      in
      line (
        [
          (pair "sys" name)
          (pair "ip" record.ip)
        ]
        ++ values "sys" record.aliases
        ++ optional "dom" record.dom
        ++ optional "ether" record.ether
        ++ optional "ipgw" record.ipgw
      )
      + builtins.concatStringsSep "" (
        map (
          address:
          "\n\t"
          + line (
            [ (pair "ip" address.ip) ]
            ++ optional "ether" (address.ether or null)
            ++ optional "ipgw" (address.ipgw or null)
          )
        ) record.extraAddresses
      )
      + "\n\t"
      + line (defaults record)
      + "\n";
    networkText =
      name:
      let
        record = networkData.${name};
      in
      line [
        (pair "ipnet" name)
        (pair "ip" record.address)
        (pair "ipmask" (builtins.concatStringsSep "." (map toString (maskParts record.prefixLength))))
      ]
      + "\n\t"
      + line (defaults record ++ optional "ipgw" record.ipgw)
      + "\n";
    dnsConfig =
      (
        {
          enable ? true,
          resolver ? true,
        }:
        {
          inherit enable resolver;
        }
      )
        dns;
    hostAddresses = builtins.concatLists (
      map (record: [ { inherit (record) ip ether ipgw; } ] ++ record.extraAddresses) (
        builtins.attrValues hostData
      )
    );
    addresses = map (record: record.ip) hostAddresses;
    aliases = builtins.concatLists (map (record: record.aliases) (builtins.attrValues hostData));
    publicReference =
      value: value == null || (safe value && builtins.match "[^[:space:]]+" value != null);
    unique =
      items:
      builtins.length items == builtins.length (
        builtins.foldl' (out: item: if builtins.elem item out then out else out ++ [ item ]) [ ] items
      );
    aligned =
      record:
      builtins.all
        (
          index:
          let
            value = builtins.fromJSON (builtins.elemAt (split record.address) index);
            block = 256 - builtins.elemAt (maskParts record.prefixLength) index;
          in
          builtins.div value block * block == value
        )
        [
          0
          1
          2
          3
        ];
  in
  if !builtins.isBool enable then
    error "enable must be a boolean"
  else if !builtins.isAttrs hosts || !builtins.all label hostNames then
    error "hosts must be keyed by unique lowercase host labels"
  else if !builtins.isAttrs networks || !builtins.all label networkNames then
    error "networks must be keyed by lowercase labels"
  else if
    !builtins.isList include
    || !builtins.all (
      path:
      safe path
      && builtins.stringLength path < 128
      && builtins.match "/[^[:space:]]+" path != null
      && path != "/lib/ndb/local"
    ) include
  then
    error "include must list absolute paths shorter than 128 bytes without whitespace; use /cfg/nix9/ndb-original for the original local database"
  else if !builtins.all (record: validIP record.ip) hostAddresses then
    error "hosts require IPv4 addresses"
  else if !unique addresses then
    error "hosts contain duplicate IPv4 addresses"
  else if !builtins.all label aliases || !unique (hostNames ++ aliases) then
    error "hosts.aliases must be unique lowercase labels distinct from canonical host names"
  else if
    !builtins.all (
      record: record.dom == null || (safe record.dom && builtins.all label (split record.dom))
    ) (builtins.attrValues hostData)
  then
    error "hosts.dom must be a lowercase DNS name"
  else if
    !builtins.all (
      record:
      (record.ether or null) == null
      || (builtins.isString record.ether && builtins.match "[0-9a-f]{12}" record.ether != null)
    ) hostAddresses
  then
    error "hosts.ether must contain twelve lowercase hexadecimal digits"
  else if
    !builtins.all (
      record:
      validIP record.address
      && builtins.isInt record.prefixLength
      && record.prefixLength >= 0
      && record.prefixLength <= 32
      && aligned record
    ) (builtins.attrValues networkData)
  then
    error "networks require aligned IPv4 addresses and prefixLength from 0 to 32"
  else if
    !builtins.all (
      record:
      builtins.all publicReference [
        record.auth
        record.fs
        record.cpu
      ]
    ) allRecords
  then
    error "auth, fs and cpu must be native server names or addresses without whitespace"
  else if
    !builtins.all (
      record:
      (record.authdom == null || safe record.authdom)
      && builtins.isList record.dns
      && builtins.all validIP record.dns
      && builtins.isList record.ntp
      && builtins.all safe record.ntp
      && builtins.all safe record.dnsdomain
    ) allRecords
  then
    error "invalid authdom, dns, dnsdomain or ntp defaults"
  else if
    !builtins.all (record: (record.ipgw or null) == null || validIP record.ipgw) (
      hostAddresses ++ builtins.attrValues networkData
    )
  then
    error "ipgw must be an IPv4 address"
  else if !builtins.isString extraConfig then
    error "extraConfig must contain native NDB text"
  else if !builtins.isString recordText then
    error "records must contain structured NDB records"
  else if !builtins.isBool dnsConfig.enable || !builtins.isBool dnsConfig.resolver then
    error "dns settings must be boolean"
  else if !enable && (hosts != { } || networks != { } || records != [ ] || extraConfig != "") then
    error "hosts, networks, records and extraConfig require enable"
  else if !enable then
    null
  else
    {
      inherit package include;
      dns = dnsConfig;
      database =
        "database=\n"
        + builtins.concatStringsSep "" (map (path: "\tfile=${quoted path}\n") include)
        + "\n"
        + builtins.concatStringsSep "\n" (map hostText hostNames ++ map networkText networkNames)
        + "\n"
        + recordText
        + "\n\n"
        + extraConfig
        + "\n";
    }
)
  configuration
