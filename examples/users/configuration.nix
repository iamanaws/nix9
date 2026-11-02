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
      ];
      speaksFor.build = [
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
    build.configuration = {
      services.cpu.allowedUsers = [
        "alice"
        "bob"
      ];
      namespace.binds = [
        {
          source = "/root/projects";
          target = "/n/projects";
          create = true;
        }
      ];
    };
  };
}
