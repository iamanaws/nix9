{ lib, ... }:
{
  imports = [ ../dns/configuration.nix ];
  name = lib.mkForce "site-lab";
  ndb = {
    hosts.terminal.ether = "525400123456";
    networks.lab = {
      address = "172.23.0.0";
      prefixLength = 24;
      dns = [ "172.23.0.10" ];
      dnsdomain = [ "lab.example.test" ];
    };
  };
  machines = {
    dns.configuration.services.dhcpd = {
      enable = true;
      pools = [
        {
          start = "172.23.0.100";
          count = 20;
        }
      ];
    };
    terminal.configuration.networking = {
      interfaces.ether0 = {
        useDHCP = lib.mkForce true;
        address = lib.mkForce null;
        prefixLength = lib.mkForce null;
      };
      nameservers = lib.mkForce [ ];
    };
  };
}
