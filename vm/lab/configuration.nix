{
  pkgs ? import <nix9>,
}:
pkgs.mkInstallation (
  { lib, ... }: {
    imports = [ <nix9/examples/users/configuration.nix> ];
    name = lib.mkForce "development";
    users.builder = {
      id = 1013;
      home = "/usr/builder";
    };
    machines = {
      auth.configuration.services.auth = {
        requiredUsers = [ "builder" ];
        speaksFor.batch = [ "builder" ];
        speaksFor.glenda = [ "builder" ];
      };
      auth.configuration.networking.interfaces.ether0 = {
        useDHCP = false;
        address = "10.0.2.100";
        prefixLength = 24;
      };
      files.configuration = {
        networking.interfaces.ether0 = {
          useDHCP = false;
          address = "10.0.2.101";
          prefixLength = 24;
        };
        services.cwfs.deviceMap = lib.mkForce {
          w0 = "/dev/sdG0/data";
          w1 = "/dev/sdH0/data";
        };
      };
      build = {
        builders.batch.user = "builder";
        configuration.nix = {
          settings.max-jobs = 0;
          daemon.keyFile = "/adm/builder.keys";
        };
      };
      batch.configuration = {
        services.cpu.allowedUsers = [ "builder" ];
        nix.settings.trusted-users = [ "builder" ];
      };
    };
  }
)
