{
  name = "builders";
  defaults = {
    auth = "auth";
    cpu = "build";
    authdom = "nix9.builders";
  };
  machines = {
    auth = {
      ip = "10.0.2.100";
      configuration = {
        networking.enable = true;
        services.auth.enable = true;
      };
    };
    build = {
      ip = "10.0.2.101";
      configuration = {
        networking.enable = true;
        services.cpu = {
          enable = true;
          allowedUsers = [ "glenda" ];
          keyFile = "/adm/cpu.keys";
          keyPattern = "dom=nix9.builders";
        };
      };
    };
    terminal = {
      ip = "10.0.2.102";
      builders.build = { };
      configuration = {
        networking.enable = true;
        nix.maxJobs = 0;
      };
    };
  };
}
