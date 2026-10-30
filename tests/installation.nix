{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        (<nix9> + "/examples/installation/configuration.nix")
        extra
      ];
    };
in
{
  valid = make { };
  deployment = make {
    machines.cpu.deployment = {
      host = "cpu-admin";
      user = "glenda";
      keyPattern = "dom=nix9.share user=glenda";
      timeout = 30;
    };
  };
  retiringCpu = make (
    { lib, ... }: {
      defaults.cpu = lib.mkForce null;
      machines.cpu = {
        deployment = {
          host = "cpu-admin";
          user = "glenda";
        };
        configuration.services.cpu = {
          enable = lib.mkForce false;
          allowedUsers = lib.mkForce [ ];
          keyFile = lib.mkForce null;
          keyPattern = lib.mkForce "";
        };
      };
    }
  );
  renamed = make {
    machines.files = {
      hostName = "storage";
      machineId = "file-id";
    };
  };
  movedPort = make {
    machines.files.configuration.services.exports.projects.port = 17025;
  };
  optional = make {
    machines.terminal.mounts.projects.required = false;
  };
  noConsumerMounts = make ({ lib, ... }: { machines.terminal.mounts = lib.mkForce { }; });
  minimal = pkgs.mkInstallation { machines.one.ip = "10.1.0.1"; };
  mutualMounts = pkgs.mkInstallation {
    machines = builtins.listToAttrs (
      map
        (name: {
          inherit name;
          value = {
            ip = if name == "one" then "10.1.0.1" else "10.1.0.2";
            configuration.services.exports.data = {
              path = "/usr/glenda/data";
              allowedUsers = [ "glenda" ];
            };
            mounts.data.provider = if name == "one" then "two" else "one";
          };
        })
        [
          "one"
          "two"
        ]
    );
  };
  empty = make ({ lib, ... }: { machines = lib.mkForce { }; });
  duplicateIdentity = make { machines.cpu.machineId = "files"; };
  duplicateHostname = make { machines.cpu.hostName = "files"; };
  duplicateAddress = make { machines.cpu.ip = "10.0.2.100"; };
  invalidAddress = make { machines.cpu.ip = "10.0.2.999"; };
  unknownProvider = make { defaults.auth = "missing"; };
  missingRole = make (
    { lib, ... }: {
      machines.cpu.configuration.services.cpu = {
        enable = lib.mkForce false;
        allowedUsers = lib.mkForce [ ];
        keyFile = lib.mkForce null;
        keyPattern = lib.mkForce "";
      };
    }
  );
  unknownMountProvider = make { machines.terminal.mounts.projects.provider = "missing"; };
  unknownExport = make { machines.terminal.mounts.projects.export = "missing"; };
  conflictingEndpoints = make {
    machines.files.configuration.services.listen = {
      enable = true;
      tcp."17020" = "echo conflict";
    };
  };
  invalidOtherMachine = make {
    machines.terminal.configuration.namespace.mounts.invalid = {
      address = "tcp!outside!17020";
      mountPoint = "/usr/local";
    };
  };
  invalidDirectory = make {
    machines.terminal.configuration.directories."/usr/local/nix/state" = { };
  };
  overriddenIdentity = make (
    { lib, ... }: {
      machines.files.configuration.machineId = lib.mkForce "different";
    }
  );
  overriddenDiscovery = make (
    { lib, ... }: {
      machines.cpu.configuration.services.ndb.hosts = lib.mkForce { };
    }
  );
  overriddenMount = make (
    { lib, ... }: {
      machines.terminal.configuration.namespace.mounts.projects.address = lib.mkForce "tcp!outside!17020";
    }
  );
  unknownOption = make { machines.cpu.unknown = true; };
  invalidDeploymentHost = make { machines.cpu.deployment.host = "cpu\necho bad"; };
  invalidDeploymentUser = make { machines.cpu.deployment.user = "*"; };
  deniedDeploymentUser = make { machines.cpu.deployment.user = "nobody"; };
  secretDeploymentPattern = make { machines.cpu.deployment.keyPattern = "!password=bad"; };
  invalidDeploymentTimeout = make { machines.cpu.deployment.timeout = 0; };
  optionalUnknownProvider = make {
    machines.terminal.mounts.projects = {
      provider = "missing";
      required = false;
    };
  };
}
