{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/netboot/configuration.nix>
        extra
      ];
    };
in
{
  initial = make { };
  tftpOnly = make (
    { lib, ... }: { machines.files.configuration.services.dhcpd.enable = lib.mkForce false; }
  );
  separateDhcp = make (
    { lib, ... }: {
      machines.files.configuration.services.dhcpd.enable = lib.mkForce false;
      machines.auth.configuration.services.dhcpd.enable = true;
    }
  );
  second =
    (import ./netroot.nix {
      inherit pkgs;
      pxe = true;
    }).second;
  invalid = {
    unknownProvider = make (
      { lib, ... }: { machines.build.boot.pxe.provider = lib.mkForce "missing"; }
    );
    selfProvider = make ({ lib, ... }: { machines.build.boot.pxe.provider = lib.mkForce "build"; });
    disabledTftp = make (
      { lib, ... }: { machines.files.configuration.services.tftpd.enable = lib.mkForce false; }
    );
    noEther = make ({ lib, ... }: { machines.build.ether = lib.mkForce null; });
    malformedEther = make ({ lib, ... }: { machines.build.ether = lib.mkForce "invalid"; });
    changedEther = make ({ lib, ... }: { ndb.hosts.build.ether = lib.mkForce "525400123499"; });
    changedTftp = make ({ lib, ... }: { ndb.hosts.build.tftp = lib.mkForce "auth"; });
    reservedSetting = make { machines.build.boot.pxe.settings.rootdir = "/other"; };
    multilineSetting = make (
      { lib, ... }: { machines.build.boot.pxe.settings.console = lib.mkForce "0\nrootdir=/other"; }
    );
    unknownOption = make { machines.build.boot.pxe.unknown = true; };
  };
  ndb = pkgs.mkSystem {
    hostName = "boot-server";
    services.ndb = {
      enable = true;
      hosts.client = {
        ip = "192.0.2.20";
        ether = "525400123456";
        bootf = "9bootpxe";
        tftp = "boot-server";
      };
      networks.lab = {
        address = "192.0.2.0";
        prefixLength = 24;
        bootf = "/boot/kernel";
        tftp = "192.0.2.10";
      };
    };
  };
  badBootFile = pkgs.mkSystem {
    hostName = "invalid";
    services.ndb = {
      enable = true;
      hosts.client = {
        ip = "192.0.2.20";
        bootf = "../kernel";
      };
    };
  };
  tftp = pkgs.mkSystem {
    hostName = "boot-server";
    services.tftpd.enable = true;
  };
  badDirectory = pkgs.mkSystem {
    hostName = "invalid";
    services.tftpd = {
      enable = true;
      directory = "/../tftp";
    };
  };
}
