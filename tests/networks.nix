{
  pkgs ? import <nix9>,
}:
let
  system =
    networking:
    pkgs.mkSystem {
      hostName = "nix9-network";
      services.webfs.enable = true;
      networking = {
        enable = true;
      }
      // networking;
    };
  static =
    extra:
    system {
      interfaces.ether0 = {
        useDHCP = false;
        address = "10.0.2.42";
        prefixLength = 25;
      }
      // extra;
    };
in
{
  dhcp = system { };
  dns = system { nameservers = [ "127.0.0.1" ]; };
  static = system {
    interfaces.ether0 = {
      useDHCP = false;
      address = "10.0.2.42";
      prefixLength = 25;
    };
    defaultGateway = "10.0.2.2";
    nameservers = [ "127.0.0.1" ];
  };
  dual = system {
    interfaces = {
      ether0 = { };
      ether1 = {
        useDHCP = false;
        address = "172.23.0.10";
        prefixLength = 24;
      };
    };
  };
  dualDHCP = system {
    interfaces = {
      ether0 = { };
      ether1 = { };
    };
  };
  secondPrimary = system {
    primaryInterface = "ether1";
    interfaces = {
      ether0 = {
        useDHCP = false;
        address = "10.0.2.42";
        prefixLength = 24;
      };
      ether1 = { };
    };
  };
  merged = pkgs.mkSystem {
    hostName = "merged";
    networking.enable = true;
    imports = [
      ({ lib, ... }: { networking.interfaces.ether0.useDHCP = lib.mkDefault true; })
      {
        networking.interfaces.ether0 = {
          useDHCP = false;
          address = "10.0.2.42";
          prefixLength = 24;
        };
      }
    ];
  };
  invalidEnable = system { enable = "yes"; };
  invalidInterface = system { interfaces."ether0; reboot" = { }; };
  invalidPrimary = system { primaryInterface = "ether0; reboot"; };
  missingPrimary = system { interfaces.ether1 = { }; };
  empty = system { interfaces = { }; };
  invalidDHCP = system { interfaces.ether0.useDHCP = "yes"; };
  mixedAddress = system { interfaces.ether0.address = "10.0.2.42"; };
  mixedPrefix = system { interfaces.ether0.prefixLength = 24; };
  missingAddress = static { address = null; };
  invalidAddress = static { address = "10.0.2.256"; };
  loopbackAddress = static { address = "127.0.0.1"; };
  multicastAddress = static { address = "224.0.0.1"; };
  missingPrefix = static { prefixLength = null; };
  invalidPrefix = static { prefixLength = 33; };
  invalidGateway = system { defaultGateway = "0.0.0.0"; };
  invalidDNS = system { nameservers = [ "10.0.2.3\nreboot" ]; };
  invalidDNSList = system { nameservers = "10.0.2.3"; };
  ambiguousDNS = system { nameservers = [ "010.0.2.3" ]; };
  duplicateAddress = system {
    interfaces = {
      ether0 = {
        useDHCP = false;
        address = "172.23.0.10";
        prefixLength = 24;
      };
      ether1 = {
        useDHCP = false;
        address = "172.23.0.10";
        prefixLength = 24;
      };
    };
  };
  unknownOption = system { interfaces.ether0.gateway = "10.0.2.2"; };
  misplacedAddress = system { address = "10.0.2.42"; };
}
