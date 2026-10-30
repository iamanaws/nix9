{ lib, ... }:
let
  ipv4 = lib.types.addCheck lib.types.str (
    value:
    let
      parts = lib.splitString "." value;
    in
    builtins.length parts == 4
    && builtins.all (
      part: builtins.match "(0|[1-9][0-9]{0,2})" part != null && builtins.fromJSON part <= 255
    ) parts
    && builtins.fromJSON (builtins.head parts) > 0
    && builtins.fromJSON (builtins.head parts) < 224
  );
  interfaceAddress = lib.types.addCheck ipv4 (value: !(lib.hasPrefix "127." value));
in
{
  options = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Configure Ethernet interfaces and native name resolution at boot.";
    };
    primaryInterface = lib.mkOption {
      type = lib.types.strMatching "ether(0|[1-9][0-9]*)";
      default = "ether0";
      description = "Interface publishing host, DHCP and DNS information in /net/ndb.";
    };
    interfaces = lib.mkOption {
      default.ether0 = { };
      description = "Ethernet interfaces configured in the native /net stack.";
      type = lib.types.attrsOf (
        lib.types.submodule {
          options = {
            useDHCP = lib.mkOption {
              type = lib.types.bool;
              default = true;
              description = "Obtain this interface's address through native DHCP, with lease renewal.";
            };
            address = lib.mkOption {
              type = lib.types.nullOr interfaceAddress;
              default = null;
              description = "Static unicast IPv4 address.";
            };
            prefixLength = lib.mkOption {
              type = lib.types.nullOr (lib.types.ints.between 1 32);
              default = null;
              description = "Static IPv4 prefix length.";
            };
          };
        }
      );
    };
    defaultGateway = lib.mkOption {
      type = lib.types.nullOr interfaceAddress;
      default = null;
      description = "Explicit gateway for the primary interface, overriding DHCP.";
    };
    nameservers = lib.mkOption {
      type = lib.types.listOf ipv4;
      default = [ ];
      description = "DNS servers overriding primary-interface DHCP, or empty to use native discovery.";
    };
  };
}
