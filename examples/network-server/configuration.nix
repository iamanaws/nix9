{ config, pkgs, ... }:
{
  name = "network-lab";
  defaults = {
    auth = "auth";
    cpu = "cpu";
    authdom = "nix9.lab";
  };
  machines = {
    auth = {
      ip = "10.0.2.100";
      configuration = {
        networking.enable = true;
        services.auth = {
          enable = true;
          speaksFor.cpu = [ "glenda" ];
        };
      };
    };
    device = {
      ip = "172.23.0.20";
      configuration = {
        networking = {
          enable = true;
          interfaces.ether0 = {
            useDHCP = false;
            address = "172.23.0.20";
            prefixLength = 24;
          };
        };
        services.listen = {
          enable = true;
          tcp."17080" = ''
            request=`{read}
            if(~ $request status) echo lab-device-ready
            if not exit 'unknown request'
          '';
        };
      };
    };
    labnet = {
      ip = "10.0.2.103";
      configuration = {
        networking = {
          enable = true;
          interfaces = {
            ether0 = { };
            ether1 = {
              useDHCP = false;
              address = "172.23.0.10";
              prefixLength = 24;
            };
          };
        };
        services.exports.lab = {
          path = "/net";
          allowedUsers = [ "glenda" ];
          readOnly = false;
          keyFile = "/adm/labnet.keys";
          keyPattern = "dom=${config.defaults.authdom} user=labnet";
        };
      };
    };
    cpu = {
      ip = "10.0.2.101";
      configuration = {
        networking.enable = true;
        packages = [ pkgs.dial ];
        services.cpu = {
          enable = true;
          allowedUsers = [ "glenda" ];
          keyFile = "/adm/cpu.keys";
          keyPattern = "dom=${config.defaults.authdom} user=cpu";
        };
      };
      mounts.lab = {
        provider = "labnet";
        mountPoint = "/n/labnet";
      };
    };
    terminal = {
      ip = "10.0.2.102";
      configuration = {
        networking.enable = true;
        packages = [ pkgs.dial ];
      };
      mounts.lab = {
        provider = "labnet";
        mountPoint = "/n/labnet";
      };
    };
  };
}
