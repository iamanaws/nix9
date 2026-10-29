{
  pkgs ? import <nix9>,
}:
let
  export = {
    path = "/usr/glenda/projects";
    allowedUsers = [ "glenda" ];
    keyFile = "/adm/files.keys";
    keyPattern = "dom=nix9.share user=files";
  };
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        (<nix9> + "/examples/installation/configuration.nix")
        {
          machines = builtins.listToAttrs (
            map
              (name: {
                inherit name;
                value.configuration = {
                  logging.enable = true;
                  logging.files.auth.mode = "0660";
                  services.timesync.enable = true;
                  services.ndb.dns.enable = false;
                };
              })
              [
                "files"
                "cpu"
                "terminal"
              ]
          );
        }
        {
          machines.files.configuration.services.exports = {
            reference = export // {
              port = 17021;
            };
            restricted = export // {
              port = 17022;
              allowedUsers = [ "nobody" ];
            };
          };
          machines.cpu.mounts.projects.timeout = 3;
          machines.terminal.mounts = {
            projects.timeout = 3;
            reference = {
              provider = "files";
              timeout = 3;
            };
          };
        }
        extra
      ];
    };
  installation = make { };
  mount = {
    address = "tcp!files!17020";
    keyPattern = "dom=nix9.share";
    timeout = 3;
  };
  invalid = configuration: pkgs.mkSystem ({ hostName = "invalid"; } // configuration);
in
{
  inherit installation;
  inherit (installation.systems) files cpu terminal;
  readOnly =
    (make (
      { lib, ... }: {
        machines.files.configuration.services.exports.projects.readOnly = lib.mkForce true;
      }
    )).systems.files;
  disabled =
    (make (
      { lib, ... }: {
        defaults.fs = lib.mkForce null;
        machines.files.configuration.services.exports = lib.mkForce { };
        machines.cpu.mounts = lib.mkForce { };
        machines.terminal.mounts = lib.mkForce { };
      }
    )).systems.files;
  moved = (make { machines.terminal.mounts.projects.mountPoint = "/n/work"; }).systems.terminal;
  optional =
    (make {
      machines.files.configuration.services.exports.unavailable = export // {
        port = 17029;
      };
      machines.terminal.mounts.absent = {
        provider = "files";
        export = "unavailable";
        required = false;
        timeout = 1;
      };
    }).systems.terminal;
  unavailable =
    (make (
      { lib, ... }: {
        machines.files.configuration.services.exports.unavailable = export // {
          port = 17029;
        };
        machines.terminal.mounts = {
          first = {
            provider = "files";
            export = "projects";
            timeout = 3;
          };
          projects = {
            export = "unavailable";
            timeout = lib.mkForce 1;
          };
        };
      }
    )).systems.terminal;
  empty = (make ({ lib, ... }: { machines.terminal.mounts = lib.mkForce { }; })).systems.terminal;

  invalidExportPath = invalid {
    services.exports.projects = export // {
      path = "relative";
    };
  };
  invalidExportUsers = invalid {
    services.exports.projects = export // {
      allowedUsers = [ ];
    };
  };
  invalidExportUser = invalid {
    services.exports.projects = export // {
      allowedUsers = [ "*" ];
    };
  };
  invalidExportPort = invalid {
    services.exports.projects = export // {
      port = 65536;
    };
  };
  duplicateExportPort = invalid {
    services.exports = {
      a = export;
      b = export;
    };
  };
  reservedExportPort = invalid {
    services.exports.projects = export // {
      port = 17019;
    };
  };
  conflictingExportPort = invalid {
    services.exports.projects = export;
    services.listen = {
      enable = true;
      tcp."17020" = "echo conflict";
    };
  };
  secretExportPattern = invalid {
    services.exports.projects = export // {
      keyPattern = "!password=test";
    };
  };
  storedExportKey = invalid {
    services.exports.projects = export // {
      keyFile = "${pkgs.rcpu}/keys";
    };
  };
  invalidMountAddress = invalid {
    namespace.mounts.projects = mount // {
      address = "files\necho bad";
    };
  };
  invalidMountPoint = invalid {
    namespace.mounts.projects = mount // {
      mountPoint = "/n/../bad";
    };
  };
  storedMountPoint = invalid {
    namespace.mounts.projects = mount // {
      mountPoint = "/usr/local/nix/store/bad";
    };
  };
  protectedMountPoint = invalid {
    namespace.mounts.projects = mount // {
      mountPoint = "/usr/local";
    };
  };
  overlappingMounts = invalid {
    namespace.mounts = {
      a = mount // {
        mountPoint = "/n/shared";
      };
      b = mount // {
        mountPoint = "/n/shared/child";
      };
    };
  };
  invalidMountTimeout = invalid {
    namespace.mounts.projects = mount // {
      timeout = 0;
    };
  };
  secretMountPattern = invalid {
    namespace.mounts.projects = mount // {
      keyPattern = "!password=test";
    };
  };
}
