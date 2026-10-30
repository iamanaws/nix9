{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/storage/configuration.nix>
        {
          machines = builtins.listToAttrs (
            map
              (name: {
                inherit name;
                value.configuration.services.ndb.dns.enable = false;
              })
              [
                "auth"
                "files"
                "build"
                "batch"
                "terminal"
              ]
          );
        }
        {
          machines.build.configuration.services.exports.tools = {
            path = "/usr/glenda";
            allowedUsers = [ "glenda" ];
            keyFile = "/adm/cpu.keys";
            keyPattern = "dom=nix9.storage user=build";
          };
          machines.terminal.mounts.tools.provider = "build";
          machines.build.mounts.history = {
            provider = "files";
            fileSystem = "dump";
          };
        }
        extra
      ];
    };
  initial = make { };
  system =
    settings:
    pkgs.mkSystem {
      hostName = "files";
      services.cwfs = {
        enable = true;
        configDevice = "/adm/storage/config";
      }
      // settings;
    };
in
{
  inherit initial;
  inherit (initial.systems)
    auth
    files
    build
    batch
    terminal
    ;
  noDumps =
    (make ({ lib, ... }: { machines.files.configuration.services.cwfs.autoDump = lib.mkForce false; }))
    .systems.files;
  invalid = {
    missingDevice = system { configDevice = null; };
    invalidHour = system { dumpHour = 24; };
    invalidCache = system { cachePercent = 0; };
    invalidDevice = system { configDevice = "/adm/../data"; };
    invalidMap = system { deviceMap."w0; reboot" = "/adm/storage/cache"; };
    disabledSettings = system { enable = false; };
    reservedPort = system { port = 567; };
    tcpConflict = pkgs.mkSystem {
      hostName = "files";
      services.cwfs = {
        enable = true;
        configDevice = "/adm/storage/config";
      };
      services.listen = {
        enable = true;
        tcp."564" = "echo collision\n";
      };
    };
    tlsAttach = pkgs.mkSystem {
      hostName = "client";
      namespace.mounts.data = {
        address = "tcp!files!564";
        attach = "main";
      };
    };
    disabledProvider =
      (make (
        { lib, ... }: { machines.files.configuration.services.cwfs = lib.mkForce { enable = false; }; }
      )).build;
  };
}
