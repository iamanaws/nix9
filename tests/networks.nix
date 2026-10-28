let
  pkgs = import <nix9>;
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
in
{
  dhcp = system { };
  dns = system { nameservers = [ "127.0.0.1" ]; };
  static = system {
    useDHCP = false;
    address = "10.0.2.42";
    prefixLength = 25;
    defaultGateway = "10.0.2.2";
    nameservers = [ "127.0.0.1" ];
  };
  invalidEnable = system { enable = "yes"; };
  invalidInterface = system { interface = "ether0; reboot"; };
  invalidDHCP = system { useDHCP = "yes"; };
  mixedAddress = system { address = "10.0.2.42"; };
  mixedPrefix = system { prefixLength = 24; };
  missingAddress = system {
    useDHCP = false;
    prefixLength = 24;
  };
  invalidAddress = system {
    useDHCP = false;
    address = "10.0.2.256";
    prefixLength = 24;
  };
  loopbackAddress = system {
    useDHCP = false;
    address = "127.0.0.1";
    prefixLength = 8;
  };
  multicastAddress = system {
    useDHCP = false;
    address = "224.0.0.1";
    prefixLength = 24;
  };
  missingPrefix = system {
    useDHCP = false;
    address = "10.0.2.42";
  };
  invalidPrefix = system {
    useDHCP = false;
    address = "10.0.2.42";
    prefixLength = 33;
  };
  invalidGateway = system { defaultGateway = "0.0.0.0"; };
  invalidDNS = system { nameservers = [ "10.0.2.3\nreboot" ]; };
  invalidDNSList = system { nameservers = "10.0.2.3"; };
  ambiguousDNS = system { nameservers = [ "010.0.2.3" ]; };
}
