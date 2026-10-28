{ hostName, configuration }:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
in
(
  {
    enable ? false,
    interface ? "ether0",
    useDHCP ? true,
    address ? null,
    prefixLength ? null,
    defaultGateway ? null,
    nameservers ? [ ],
  }:
  let
    octets = ip: builtins.filter builtins.isString (builtins.split "\\." ip);
    validIP =
      ip:
      builtins.isString ip
      && builtins.length (octets ip) == 4
      && builtins.all (
        part: builtins.match "(0|[1-9][0-9]{0,2})" part != null && builtins.fromJSON part <= 255
      ) (octets ip)
      && builtins.fromJSON (builtins.head (octets ip)) > 0
      && builtins.fromJSON (builtins.head (octets ip)) < 224;
    validEthernetIP = ip: validIP ip && builtins.head (octets ip) != "127";
    error = message: throw "mkSystem: networking.${message}";
    gatewayFlags = if defaultGateway == null then "" else "-O -g ${quote defaultGateway}";
    dnsFlags = builtins.concatStringsSep " " (map (ip: "-s ${quote ip}") nameservers);
    addressFlags = if useDHCP then "" else "${quote address} /${toString prefixLength}";
  in
  if !builtins.isBool enable then
    error "enable must be a boolean"
  else if !builtins.isString interface || builtins.match "ether[0-9]+" interface == null then
    error "interface must name an Ethernet device, such as ether0"
  else if !builtins.isBool useDHCP then
    error "useDHCP must be a boolean"
  else if useDHCP && (address != null || prefixLength != null) then
    error "useDHCP cannot be combined with a static address or prefixLength"
  else if !useDHCP && (!validEthernetIP address) then
    error "address must be a unicast IPv4 address when useDHCP is false"
  else if !useDHCP && (!builtins.isInt prefixLength || prefixLength < 1 || prefixLength > 32) then
    error "prefixLength must be an integer from 1 to 32 when useDHCP is false"
  else if defaultGateway != null && !validEthernetIP defaultGateway then
    error "defaultGateway must be a unicast IPv4 address"
  else if !builtins.isList nameservers || !builtins.all validIP nameservers then
    error "nameservers must be a list of unicast IPv4 addresses"
  else if !enable then
    ""
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
        ip/ipconfig -p -h ${quote hostName} ${gatewayFlags} ${dnsFlags} ether /net/${interface} ${addressFlags} || fail ${quote interface}
        DNSSERVER=()
        DOTSERVER=()
        ${
          if nameservers == [ ] then "" else "DNSSERVER=${quote (builtins.concatStringsSep " " nameservers)}"
        }
        ndb/cs || fail 'connection service'
        ndb/dns -r || fail 'DNS resolver'
        echo 'nix9: networking ready on ${interface}'
      }
    ''
)
  configuration
