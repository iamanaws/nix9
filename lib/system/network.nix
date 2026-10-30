{
  lib,
  hostName,
  configuration,
}:
let
  inherit (configuration)
    enable
    interfaces
    primaryInterface
    defaultGateway
    nameservers
    ;
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  names = builtins.attrNames interfaces;
  error = message: throw "mkSystem: networking.${message}";
  addresses = map (interface: interface.address) (
    builtins.filter (interface: !interface.useDHCP) (builtins.attrValues interfaces)
  );
  configure =
    name:
    let
      interface = interfaces.${name};
      primary = name == primaryInterface;
      flags = lib.optionals primary (
        lib.optional (defaultGateway != null) "-O -g ${quote defaultGateway}"
        ++ map (ip: "-s ${quote ip}") nameservers
      );
      address = lib.optionalString (
        !interface.useDHCP
      ) "${quote interface.address} /${toString interface.prefixLength}";
    in
    ''
      if(! test -d /net/${name})
        bind -a ${quote ("#l" + lib.removePrefix "ether" name)} /net || fail ${quote ("attach " + name)}
      ip/ipconfig ${
        if primary then "-p" else "-P"
      } -h ${quote hostName} ${lib.concatStringsSep " " flags} ether /net/${name} ${address} || fail ${quote name}
    '';
in
if !enable then
  ""
else if !builtins.all (name: builtins.match "ether(0|[1-9][0-9]*)" name != null) names then
  error "interfaces must be keyed by Ethernet devices, such as ether0"
else if !(builtins.hasAttr primaryInterface interfaces) then
  error "primaryInterface must name a configured interface"
else if
  builtins.any (
    interface: interface.useDHCP && (interface.address != null || interface.prefixLength != null)
  ) (builtins.attrValues interfaces)
then
  error "interfaces.useDHCP cannot be combined with a static address or prefixLength"
else if
  builtins.any (
    interface: !interface.useDHCP && (interface.address == null || interface.prefixLength == null)
  ) (builtins.attrValues interfaces)
then
  error "interfaces require address and prefixLength when useDHCP is false"
else if builtins.length addresses != builtins.length (lib.unique addresses) then
  error "interfaces must use distinct static addresses"
else
  ''
    # Boot only: switching generations must not interrupt a live connection.
    @{
      rfork e
      fn fail {
        echo 'nix9: networking failed:' $* >[1=2]
        exit 'networking failed'
      }
      if(test -e /srv/cs || test -e /srv/dns || test -e /net/cs || test -e /net/dns)
        fail 'cs or dns was started before the managed boot hook'
      ip/ipconfig -P loopback /dev/null 127.1 || fail 'IPv4 loopback'
      ip/ipconfig -P loopback /dev/null ::1 || fail 'IPv6 loopback'
      ${lib.concatMapStrings configure ([ primaryInterface ] ++ lib.remove primaryInterface names)}
      DNSSERVER=()
      DOTSERVER=()
      ${lib.optionalString (
        nameservers != [ ]
      ) "DNSSERVER=${quote (lib.concatStringsSep " " nameservers)}"}
      ndb/cs || fail 'connection service'
      ndb/dns -r || fail 'DNS resolver'
      echo 'nix9: networking ready on' ${lib.concatMapStringsSep " " quote names}
    }
  ''
