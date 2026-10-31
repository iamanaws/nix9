{
  name = "workstation";
  defaults = {
    auth = "auth";
    fs = "files";
    cpu = "build";
    authdom = "nix9.workstation";
  };
  machines = {
    auth = {
      ip = "10.0.2.100";
      configuration = {
        networking.enable = true;
        services.auth.enable = true;
      };
    };
    files = {
      ip = "10.0.2.101";
      configuration = {
        networking.enable = true;
        directories."/usr/glenda/projects".mode = "0750";
        services.exports.projects = {
          path = "/usr/glenda/projects";
          readOnly = false;
          allowedUsers = [ "glenda" ];
          keyFile = "/adm/files.keys";
          keyPattern = "dom=nix9.workstation user=files";
        };
      };
    };
    build = {
      ip = "10.0.2.102";
      configuration = {
        networking.enable = true;
        services.cpu = {
          enable = true;
          allowedUsers = [ "glenda" ];
          keyFile = "/adm/cpu.keys";
          keyPattern = "dom=nix9.workstation user=build";
        };
      };
    };
    terminal = {
      ip = "10.0.2.103";
      mounts.projects.provider = "files";
      builders.build.maxJobs = 2;
      configuration = {
        networking.enable = true;
        nix.maxJobs = 0;
        session = {
          enable = true;
          acme = {
            directory = "/n/projects/hello";
            files = [
              "hello.c"
              "default.nix"
            ];
            rectangle = [
              8
              8
              1016
              540
            ];
          };
          windows = [
            {
              directory = "/n/projects/hello";
              rectangle = [
                8
                548
                1016
                760
              ];
            }
          ];
        };
      };
    };
  };
}
