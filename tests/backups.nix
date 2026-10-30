{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/backup/configuration.nix>
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
                "backup"
              ]
          );
          jobs.projects-backup.schedule = pkgs.lib.mkForce "0 0 1 1 *";
        }
        {
          machines.build.configuration.services.exports.tools = {
            path = "/usr/glenda";
            allowedUsers = [ "glenda" ];
            keyFile = "/adm/cpu.keys";
            keyPattern = "dom=nix9.storage user=build";
          };
          machines.terminal.mounts.tools.provider = "build";
        }
        extra
      ];
    };
  initial = make { };
  invalid =
    settings:
    (make {
      machines.build.configuration.services.backups.projects = settings;
    }).build;
in
{
  inherit initial;
  inherit (initial.systems)
    auth
    files
    build
    batch
    terminal
    backup
    ;
  noDumps =
    (make (
      { lib, ... }: {
        machines.files.configuration.services.cwfs.autoDump = lib.mkForce false;
      }
    )).systems.files;
  invalid = {
    missingSource = invalid { sourceMount = "missing"; };
    writableSource = invalid { sourceMount = "work"; };
    missingDestination = invalid { destinationMount = "missing"; };
    nativeDestination = invalid { destinationMount = "work"; };
    noPaths = invalid { paths = pkgs.lib.mkForce [ ]; };
    traversal = invalid { paths = pkgs.lib.mkForce [ "../projects" ]; };
    prototypeWildcard = invalid { paths = pkgs.lib.mkForce [ "+" ]; };
    duplicate = invalid {
      paths = pkgs.lib.mkForce [
        "projects"
        "projects"
      ];
    };
    overlap = invalid {
      paths = pkgs.lib.mkForce [
        "projects"
        "projects/sub"
      ];
    };
    badName =
      (make {
        machines.build.configuration.services.backups."bad/name" = {
          sourceMount = "history";
          destinationMount = "archives";
          paths = [ "projects" ];
        };
      }).build;
  };
}
