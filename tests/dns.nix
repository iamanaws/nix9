{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/dns/configuration.nix>
        {
          machines.dns.configuration.services.ndb.dns.listenAddresses = [ "10.0.2.15" ];
          ndb.records = [
            {
              dom = "outside.test";
              ip = "192.0.2.200";
            }
          ];
        }
        extra
      ];
    };
  initial = make { };
in
{
  inherit initial;
  changed = make (
    { lib, ... }: {
      ndb.hosts.build.ip = lib.mkForce "172.23.0.31";
      machines.dns.configuration.services.ndb.dns.recursion = lib.mkForce "all";
    }
  );
  local = make (
    { lib, ... }: {
      machines.dns.configuration.services.ndb.dns = {
        listenAddresses = lib.mkForce [ "*" ];
        recursion = lib.mkForce "local";
      };
    }
  );
  localOnly = make (
    { lib, ... }: {
      machines.dns.configuration.services.ndb.dns.listenAddresses = lib.mkForce [ ];
    }
  );
  disabled = make (
    { lib, ... }: {
      machines.dns.configuration.services.ndb.dns = {
        enable = false;
        listenAddresses = lib.mkForce [ ];
      };
    }
  );
  badAddress = make {
    machines.dns.configuration.services.ndb.dns.listenAddresses = [ "999.1.1.1" ];
  };
  multicastAddress = make {
    machines.dns.configuration.services.ndb.dns.listenAddresses = [ "224.0.0.1" ];
  };
  unspecifiedAddress = make {
    machines.dns.configuration.services.ndb.dns.listenAddresses = [ "0.0.0.0" ];
  };
  duplicateAddress = make {
    machines.dns.configuration.services.ndb.dns.listenAddresses = [ "172.23.0.10" ];
  };
  wildcardWithAddress = make {
    machines.dns.configuration.services.ndb.dns.listenAddresses = [ "*" ];
  };
  badPolicy = make (
    { lib, ... }: {
      machines.dns.configuration.services.ndb.dns.recursion = lib.mkForce "public";
    }
  );
  disabledListener = make { machines.dns.configuration.services.ndb.dns.enable = false; };
  disabledNdb = pkgs.mkSystem {
    hostName = "invalid";
    services.ndb.dns.listenAddresses = [ "127.0.0.1" ];
  };
  tcpConflict = make {
    machines.dns.configuration.services.listen = {
      enable = true;
      tcp."53" = "echo conflict";
    };
  };
  exportConflict = make {
    machines.dns.configuration.services.exports.conflict = {
      path = "/tmp";
      port = 53;
      allowedUsers = [ "glenda" ];
    };
  };
  cwfsConflict = make {
    machines.dns.configuration.services.cwfs = {
      enable = true;
      port = 53;
      configDevice = "/adm/storage/config";
    };
  };
}
