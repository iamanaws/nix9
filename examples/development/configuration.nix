{
  imports = [ ../users/configuration.nix ];
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
