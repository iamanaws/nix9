{
  pkgs ? import <nix9>,
}:
let
  base = name: {
    hostName = name;
    machineId = name;
    networking.enable = true;
    logging.enable = true;
    logging.files.auth.mode = "0660";
    services.timesync.enable = true;
    services.ndb = {
      enable = true;
      dns.enable = false;
      hosts = {
        files.ip = "10.0.2.100";
        cpu.ip = "10.0.2.101";
        terminal.ip = "10.0.2.102";
      };
      networks.lab = {
        address = "10.0.2.0";
        prefixLength = 24;
        auth = "files";
        fs = "files";
        cpu = "cpu";
        authdom = "nix9.share";
      };
    };
  };
  export = {
    path = "/usr/glenda/projects";
    allowedUsers = [ "glenda" ];
    keyFile = "/adm/files.keys";
    keyPattern = "dom=nix9.share user=files";
  };
  fileServer =
    readOnly: enabled:
    pkgs.mkSystem {
      imports = [ (base "files") ];
      services.auth = {
        enable = true;
        speaksFor.cpu = [ "glenda" ];
      };
      services.exports =
        if enabled then
          {
            projects = export // {
              inherit readOnly;
            };
            reference = export // {
              port = 17021;
            };
            restricted = export // {
              port = 17022;
              allowedUsers = [ "nobody" ];
            };
          }
        else
          { };
    };
  mount = {
    address = "tcp!files!17020";
    keyPattern = "dom=nix9.share";
    timeout = 3;
  };
  client =
    name: extra:
    pkgs.mkSystem {
      imports = [
        (base name)
        extra
      ];
      namespace.mounts.projects = mount;
    };
  invalid = configuration: pkgs.mkSystem ({ hostName = "invalid"; } // configuration);
in
{
  files = fileServer false true;
  readOnly = fileServer true true;
  disabled = fileServer true false;
  cpu = client "cpu" {
    services.cpu = {
      enable = true;
      allowedUsers = [ "glenda" ];
      keyFile = "/adm/cpu.keys";
      keyPattern = "dom=nix9.share user=cpu";
    };
  };
  terminal = client "terminal" {
    namespace.mounts.reference = mount // {
      address = "tcp!files!17021";
    };
  };
  moved = client "terminal" {
    namespace.mounts.projects.mountPoint = "/n/work";
  };
  optional = client "terminal" {
    namespace.mounts.absent = mount // {
      address = "tcp!files!17029";
      required = false;
      timeout = 1;
    };
  };
  unavailable = client "terminal" (
    { lib, ... }: {
      namespace.mounts.first = mount;
      namespace.mounts.projects.address = lib.mkForce "tcp!files!17029";
      namespace.mounts.projects.timeout = lib.mkForce 1;
    }
  );
  empty = pkgs.mkSystem { imports = [ (base "terminal") ]; };

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
