{
  pkgs ? import <nix9>,
}:
pkgs.mkInstallation (
  { lib, ... }: {
    imports = [ <nix9/examples/users/configuration.nix> ];
    name = lib.mkForce "development";
    machines = {
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
    };
  }
)
