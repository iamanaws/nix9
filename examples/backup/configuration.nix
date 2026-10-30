{ pkgs, lib, ... }:
{
  imports = [ ../storage/configuration.nix ];
  name = lib.mkForce "backup";
  machines = {
    auth.configuration.services.cron.keyFile = "/adm/scheduler.keys";
    backup = {
      ip = "10.0.2.105";
      configuration = {
        networking.enable = true;
        directories."/usr/glenda/archives" = {
          mode = "0700";
          owner = "glenda";
        };
        services.exports.archives = {
          path = "/usr/glenda/archives";
          port = 17021;
          readOnly = false;
          allowedUsers = [ "glenda" ];
          keyFile = "/adm/backup.keys";
          keyPattern = "dom=nix9.storage user=backup";
        };
      };
    };
    build = {
      mounts = {
        history = {
          provider = "files";
          fileSystem = "dump";
          required = false;
        };
        archives = {
          provider = "backup";
          required = false;
        };
      };
      configuration.services.backups.projects = {
        sourceMount = "history";
        destinationMount = "archives";
        paths = [ "projects" ];
      };
    };
    terminal = {
      mounts.archives.provider = "backup";
      configuration.packages = [ pkgs.diskArchive ];
    };
  };
  jobs.projects-backup = {
    scheduler = "auth";
    target = "build";
    user = "glenda";
    schedule = "0 6 * * *";
    command = "exec rc $nix9System/services/backups/projects/run";
  };
}
