{ lib, ... }:
let
  workspace = {
    mounts.work = {
      provider = "files";
      fileSystem = "main";
    };
    configuration = {
      networking.enable = true;
      directories."/usr/glenda/work".mode = "0750";
      namespace.binds = [
        {
          source = "/n/work/projects";
          target = "/usr/glenda/work";
          create = true;
        }
      ];
    };
  };
  cpu = lib.recursiveUpdate workspace {
    configuration.services.cpu = {
      enable = true;
      allowedUsers = [ "glenda" ];
      keyFile = "/adm/cpu.keys";
      keyPattern = "dom=nix9.storage";
    };
  };
in
{
  name = "storage";
  defaults = {
    auth = "auth";
    fs = "files";
    cpu = "build";
    authdom = "nix9.storage";
  };
  machines = {
    auth = {
      ip = "10.0.2.100";
      configuration = {
        networking.enable = true;
        services.auth = {
          enable = true;
          speaksFor = {
            build = [ "glenda" ];
            batch = [ "glenda" ];
          };
        };
      };
    };
    files = {
      ip = "10.0.2.101";
      configuration = {
        networking.enable = true;
        services.cwfs = {
          enable = true;
          configDevice = "/adm/storage/config";
          deviceMap = {
            w0 = "/adm/storage/cache";
            w1 = "/adm/storage/worm";
          };
          keyFile = "/adm/files.keys";
        };
      };
    };
    build = cpu // {
      ip = "10.0.2.102";
    };
    batch = cpu // {
      ip = "10.0.2.103";
    };
    terminal = lib.recursiveUpdate workspace {
      ip = "10.0.2.104";
      mounts.history = {
        provider = "files";
        fileSystem = "dump";
        mountPoint = "/n/history";
      };
    };
  };
}
