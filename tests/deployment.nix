{
  pkgs ? import <nix9>,
}:
let
  make =
    revision: extra:
    pkgs.mkInstallation {
      imports = [
        (<nix9> + "/examples/installation/configuration.nix")
        ({ lib, ... }: {
          machines = builtins.listToAttrs (
            map
              (name: {
                inherit name;
                value = {
                  deployment.timeout = lib.mkDefault 120;
                  configuration = {
                    services.ndb.dns.enable = false;
                    logging.enable = true;
                    logging.files.auth.mode = "0660";
                    files.deployment = revision + "\n";
                  };
                };
              })
              [
                "files"
                "cpu"
                "terminal"
              ]
          );
        })
        {
          machines.files.configuration.services.cron.keyFile = "/adm/scheduler.keys";
          jobs.report = {
            scheduler = "files";
            target = "cpu";
            schedule = "0 0 1 1 0";
            user = "glenda";
            command = "echo ${revision}";
          };
          machines.cpu.mounts.projects.timeout = 3;
          machines.terminal.mounts.projects.timeout = 3;
        }
        extra
      ];
    };
in
{
  one = make "one" { };
  two = make "two" { };
  wrong = make "wrong" { machines.cpu.machineId = "wrong-cpu"; };
  unreachable = make "unreachable" {
    machines.cpu.deployment = {
      host = "127.0.0.1";
      timeout = 1;
    };
  };
}
