let
  cpu = { config, pkgs, ... }: {
    packages = [ pkgs.fortune ];
    directories."/tmp".mode = "0777";
    services.cpu = {
      enable = true;
      allowedUsers = [
        "alice"
        "bob"
      ];
      keyFile = "/adm/cpu.keys";
      keyPattern = "dom=nix9.netroot user=${config.hostName}";
    };
    nix = {
      daemon = {
        enable = true;
        keyPattern = config.services.cpu.keyPattern;
      };
      settings.allowed-users = [
        "alice"
        "bob"
      ];
    };
    namespace.binds = [
      {
        source = "/root/projects";
        target = "/n/projects";
        create = true;
      }
    ];
  };
in
{
  imports = [ ../netroot/configuration.nix ];
  users = {
    alice = {
      id = 1010;
      home = "/usr/alice";
    };
    bob = {
      id = 1011;
      home = "/usr/bob";
    };
    project = {
      id = 1012;
      leader = "alice";
      members = [
        "alice"
        "bob"
      ];
    };
  };
  machines = {
    auth.configuration.services.auth = {
      requiredUsers = [
        "alice"
        "bob"
        "glenda"
        "files"
        "build"
        "batch"
      ];
      speaksFor.build = [
        "alice"
        "bob"
      ];
      speaksFor.batch = [
        "glenda"
        "alice"
        "bob"
      ];
      # The example's native root boot uses this NVRAM identity.
      speaksFor.glenda = [
        "alice"
        "bob"
      ];
    };
    files.configuration.services.cwfs.directories."/projects" = {
      owner = "alice";
      group = "project";
      mode = "0770";
    };
    build.configuration = cpu;
    batch = {
      ip = "10.0.2.103";
      boot = {
        provider = "files";
        root = "stable";
      };
      configuration = {
        imports = [ cpu ];
        networking = {
          enable = true;
          interfaces.ether0 = {
            useDHCP = false;
            address = "10.0.2.103";
            prefixLength = 24;
          };
          defaultGateway = "10.0.2.2";
        };
        services.cpu.allowedUsers = [ "glenda" ];
      };
    };
  };
}
