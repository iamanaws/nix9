{
  lib,
  configuration,
  ndb,
  networking,
  package,
}:
let
  inherit (configuration)
    enable
    pools
    minimumLease
    staticLease
    ;
  error = message: throw "mkSystem: services.dhcpd.${message}";
  number =
    value:
    lib.foldl' (result: part: result * 256 + builtins.fromJSON part) 0 (lib.splitString "." value);
  ranges = map (pool: {
    first = number pool.start;
    last = number pool.start + pool.count - 1;
  }) pools;
  contains = range: value: value >= range.first && value <= range.last;
  overlaps = first: second: first.first <= second.last && second.first <= first.last;
  hostAddresses = lib.concatMap (host: [ host.ip ] ++ map (address: address.ip) host.extraAddresses) (
    builtins.attrValues ndb.hosts
  );
  staticAddresses = map (interface: interface.address) (
    builtins.filter (interface: !interface.useDHCP && interface.address != null) (
      builtins.attrValues networking.interfaces
    )
  );
  power = count: if count == 0 then 1 else 2 * power (count - 1);
  boundaries = lib.concatMap (
    network:
    lib.optionals (network.prefixLength <= 30) [
      (number network.address)
      (number network.address + power (32 - network.prefixLength) - 1)
    ]
  ) (builtins.attrValues ndb.networks);
  reserved = map number (hostAddresses ++ staticAddresses) ++ boundaries;
in
if !enable then
  if pools != [ ] || minimumLease != 900 || staticLease != 1800 then
    error "settings require enable"
  else
    null
else if !ndb.enable then
  error "enable requires services.ndb.enable"
else if
  builtins.any (
    range:
    range.last >= 3758096384
    || overlaps range {
      first = 2130706432;
      last = 2147483647;
    }
  ) ranges
then
  error "pools must contain only unicast IPv4 addresses outside loopback"
else if
  builtins.any (range: builtins.length (builtins.filter (overlaps range) ranges) != 1) ranges
then
  error "pools must not overlap"
else if builtins.any (range: builtins.any (contains range) reserved) ranges then
  error "pools must not contain NDB host addresses, configured static addresses, or declared network/broadcast addresses"
else
  {
    start = ''
      # Boot only; the daemon keeps this generation's database and namespace.
      ${package}/bin/ip/dhcpd -n -f $nix9System/ndb/local \
        -M ${toString minimumLease} -Z ${toString staticLease} ${
          lib.concatMapStringsSep " " (pool: "${pool.start} ${toString pool.count}") pools
        }
    '';
  }
