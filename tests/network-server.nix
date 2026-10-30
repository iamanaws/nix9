{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/network-server/configuration.nix>
        {
          machines = builtins.listToAttrs (
            map
              (name: {
                inherit name;
                value.configuration.services.ndb.dns.enable = false;
              })
              [
                "auth"
                "labnet"
                "cpu"
                "terminal"
                "device"
              ]
          );
        }
        {
          machines.cpu.mounts.lab.timeout = 2;
          machines.terminal.mounts.lab.timeout = 2;
          machines.labnet.configuration.services.exports = {
            restricted = {
              path = "/net";
              port = 17021;
              allowedUsers = [ "nobody" ];
              readOnly = false;
              keyFile = "/adm/labnet.keys";
              keyPattern = "dom=nix9.lab user=labnet";
            };
            readonly = {
              path = "/net";
              port = 17022;
              allowedUsers = [ "glenda" ];
              keyFile = "/adm/labnet.keys";
              keyPattern = "dom=nix9.lab user=labnet";
            };
          };
        }
        extra
      ];
    };
  initial = make { };
in
{
  inherit initial;
  inherit (initial.systems)
    auth
    labnet
    cpu
    terminal
    device
    ;
  moved =
    (make (
      { lib, ... }: {
        machines.labnet.configuration.networking.interfaces.ether1.address = lib.mkForce "172.23.0.11";
      }
    )).systems.labnet;
  disabled =
    (make (
      { lib, ... }: {
        machines.labnet.configuration.services.exports = lib.mkForce { };
        machines.cpu.mounts = lib.mkForce { };
        machines.terminal.mounts = lib.mkForce { };
      }
    )).systems.labnet;
}
