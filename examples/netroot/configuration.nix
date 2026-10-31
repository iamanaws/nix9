{
  name = "netroot";
  roots.stable = { };
  defaults = {
    auth = "auth";
    fs = "files";
    cpu = "build";
    authdom = "nix9.netroot";
  };
  machines = {
    auth = {
      ip = "10.0.2.100";
      configuration = {
        networking.enable = true;
        services.auth = {
          enable = true;
          speaksFor.build = [ "glenda" ];
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
    build = {
      ip = "10.0.2.102";
      boot.provider = "files";
      boot.root = "stable";
      configuration = {
        networking = {
          enable = true;
          interfaces.ether0 = {
            useDHCP = false;
            address = "10.0.2.102";
            prefixLength = 24;
          };
          defaultGateway = "10.0.2.2";
        };
        services.cpu = {
          enable = true;
          allowedUsers = [ "glenda" ];
          keyFile = "/adm/cpu.keys";
          keyPattern = "dom=nix9.netroot user=build";
        };
      };
    };
  };
}
