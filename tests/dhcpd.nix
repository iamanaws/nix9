{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/lab/configuration.nix>
        {
          ndb.networks.lab = {
            ipgw = "172.23.0.1";
            fs = "172.23.0.11";
            auth = "172.23.0.12";
            ntp = [ "172.23.0.13" ];
          };
          machines.dns.configuration.services.dhcpd = {
            minimumLease = 30;
            staticLease = 30;
          };
        }
        extra
      ];
    };
  server = extra: make { machines.dns.configuration = extra; };
in
{
  initial = make { };
  changed = make (
    { lib, ... }: {
      machines.terminal.ip = lib.mkForce "172.23.0.21";
    }
  );
  reservations = server (
    { lib, ... }: {
      services.dhcpd.pools = lib.mkForce [ ];
    }
  );
  disabled = server (
    { lib, ... }: {
      services.dhcpd = {
        enable = lib.mkForce false;
        pools = lib.mkForce [ ];
        minimumLease = lib.mkForce 900;
        staticLease = lib.mkForce 1800;
      };
    }
  );
  visitor = pkgs.mkSystem {
    hostName = "visitor";
    networking.enable = true;
  };
  automaticNdb = pkgs.mkSystem {
    hostName = "dhcp-server";
    services.dhcpd.enable = true;
  };
  multiplePools = server {
    services.dhcpd.pools = [
      {
        start = "192.0.2.100";
        count = 10;
      }
    ];
  };
  rawNetwork = pkgs.mkSystem {
    hostName = "raw-network";
    services = {
      ndb.extraConfig = "ipnet=raw ip=192.0.2.0 ipmask=255.255.255.0";
      dhcpd = {
        enable = true;
        pools = [
          {
            start = "192.0.2.100";
            count = 10;
          }
        ];
      };
    };
  };
  badAddress = server {
    services.dhcpd.pools = [
      {
        start = "999.0.0.1";
        count = 1;
      }
    ];
  };
  loopback = server {
    services.dhcpd.pools = [
      {
        start = "127.0.0.1";
        count = 1;
      }
    ];
  };
  multicast = server {
    services.dhcpd.pools = [
      {
        start = "224.0.0.1";
        count = 1;
      }
    ];
  };
  badCount = server {
    services.dhcpd.pools = [
      {
        start = "192.0.2.100";
        count = 0;
      }
    ];
  };
  overflow = server {
    services.dhcpd.pools = [
      {
        start = "223.255.255.255";
        count = 2;
      }
    ];
  };
  crossesLoopback = server {
    services.dhcpd.pools = [
      {
        start = "126.255.255.255";
        count = 16777218;
      }
    ];
  };
  overlap = server {
    services.dhcpd.pools = [
      {
        start = "172.23.0.110";
        count = 20;
      }
    ];
  };
  reservationConflict = server {
    services.dhcpd.pools = [
      {
        start = "172.23.0.20";
        count = 1;
      }
    ];
  };
  hostConflict = server {
    services.dhcpd.pools = [
      {
        start = "172.23.0.30";
        count = 1;
      }
    ];
  };
  staticConflict = server {
    networking.interfaces.ether2 = {
      useDHCP = false;
      address = "172.23.0.90";
      prefixLength = 24;
    };
    services.dhcpd.pools = [
      {
        start = "172.23.0.90";
        count = 1;
      }
    ];
  };
  networkAddress = server {
    services.dhcpd.pools = [
      {
        start = "172.23.0.0";
        count = 1;
      }
    ];
  };
  broadcastAddress = server {
    services.dhcpd.pools = [
      {
        start = "172.23.0.255";
        count = 1;
      }
    ];
  };
  disabledNdb = server { services.ndb.enable = false; };
  explicitlyDisabledNdb = pkgs.mkSystem {
    hostName = "invalid";
    services = {
      dhcpd.enable = true;
      ndb.enable = false;
    };
  };
  disabledSettings = pkgs.mkSystem {
    hostName = "invalid";
    services.dhcpd.pools = [
      {
        start = "192.0.2.100";
        count = 1;
      }
    ];
  };
  badLease = server { services.dhcpd.minimumLease = 0; };
  unknownOption = server { services.dhcpd.interfaces = [ "ether1" ]; };
}
