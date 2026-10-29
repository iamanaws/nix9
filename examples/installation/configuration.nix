{ config, ... }:
{
  name = "lab";
  defaults = {
    auth = "files";
    fs = "files";
    cpu = "cpu";
    authdom = "nix9.share";
  };
  machines = {
    files = {
      ip = "10.0.2.100";
      configuration = {
        networking.enable = true;
        directories."/usr/glenda/projects".mode = "0750";
        services.auth = {
          enable = true;
          speaksFor.cpu = [ "glenda" ];
        };
        services.exports.projects = {
          path = "/usr/glenda/projects";
          allowedUsers = [ "glenda" ];
          readOnly = false;
          keyFile = "/adm/files.keys";
          keyPattern = "dom=${config.defaults.authdom} user=files";
        };
      };
    };
    cpu = {
      ip = "10.0.2.101";
      configuration = {
        networking.enable = true;
        services.cpu = {
          enable = true;
          allowedUsers = [ "glenda" ];
          keyFile = "/adm/cpu.keys";
          keyPattern = "dom=${config.defaults.authdom} user=cpu";
        };
      };
      mounts.projects.provider = "files";
    };
    terminal = {
      ip = "10.0.2.102";
      configuration.networking.enable = true;
      mounts.projects.provider = "files";
    };
  };
}
