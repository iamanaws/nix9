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
    include ? [
      "/lib/ndb/common"
      "/cfg/nix9/ndb-original"
    ],
    dns ? { },
  }:
  let
    host =
      {
        ip,
        dom ? null,
        ether ? null,
        auth ? null,
        fs ? null,
        cpu ? null,
        authdom ? null,
        dns ? [ ],
        ntp ? [ ],
      }:
      {
        inherit
          ip
          dom
          ether
          auth
          fs
          cpu
          authdom
          dns
          ntp
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
          ;
      };
    hostNames = builtins.attrNames hosts;
    networkNames = builtins.attrNames networks;
    hostData = builtins.mapAttrs (_: host) hosts;
    networkData = builtins.mapAttrs (_: network) networks;
    allRecords = builtins.attrValues hostData ++ builtins.attrValues networkData;
    references =
      record:
      builtins.filter (value: value != null) [
        record.auth
        record.fs
        record.cpu
      ];
    defaults =
      record:
      optional "auth" record.auth
      ++ optional "fs" record.fs
      ++ optional "cpu" record.cpu
      ++ optional "authdom" record.authdom
      ++ values "dns" record.dns
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
        ++ optional "dom" record.dom
        ++ optional "ether" record.ether
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
      + line (defaults record)
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
    addresses = map (record: record.ip) (builtins.attrValues hostData);
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
  else if !builtins.all (record: validIP record.ip) (builtins.attrValues hostData) then
    error "hosts require IPv4 addresses"
  else if !unique addresses then
    error "hosts contain duplicate IPv4 addresses"
  else if
    !builtins.all (
      record: record.dom == null || (safe record.dom && builtins.all label (split record.dom))
    ) (builtins.attrValues hostData)
  then
    error "hosts.dom must be a lowercase DNS name"
  else if
    !builtins.all (
      record:
      record.ether == null
      || (builtins.isString record.ether && builtins.match "[0-9a-f]{12}" record.ether != null)
    ) (builtins.attrValues hostData)
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
      builtins.all (name: builtins.isString name && builtins.hasAttr name hostData) (references record)
    ) allRecords
  then
    error "auth, fs and cpu must refer to declared hosts"
  else if
    !builtins.all (
      record:
      (record.authdom == null || safe record.authdom)
      && builtins.isList record.dns
      && builtins.all validIP record.dns
      && builtins.isList record.ntp
      && builtins.all safe record.ntp
    ) allRecords
  then
    error "invalid authdom, dns or ntp defaults"
  else if !builtins.isBool dnsConfig.enable || !builtins.isBool dnsConfig.resolver then
    error "dns settings must be boolean"
  else if !enable && (hosts != { } || networks != { }) then
    error "hosts and networks require enable"
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
        + builtins.concatStringsSep "\n" (map hostText hostNames ++ map networkText networkNames);
    }
)
  configuration
