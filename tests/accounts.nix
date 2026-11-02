{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/users/configuration.nix>
        ({ lib, ... }: {
          machines.auth.configuration.services.ndb.dns.enable = false;
          machines.files.configuration.services.ndb.dns.enable = false;
          machines.build.configuration.services.ndb.dns.enable = false;
          machines.batch.configuration.services.ndb.dns.enable = false;
          machines.files.configuration.services.cpu = {
            enable = true;
            allowedUsers = [ "glenda" ];
            keyFile = "/adm/files.keys";
            keyPattern = "dom=nix9.netroot user=files";
          };
          machines.files.configuration.services.cwfs.deviceMap = lib.mkForce {
            w0 = "/dev/sdG0/data";
            w1 = "/dev/sdH0/data";
          };
          roots.stable.files."sys/lib/tls/webfs/revoked" = "";
        })
        extra
      ];
    };
in
{
  first = make { };
  second = make (
    { lib, ... }: {
      users.carol.id = 1013;
      users.project.members = lib.mkForce [ "alice" ];
    }
  );
  third = make (
    { lib, ... }: {
      users = lib.mkForce {
        alice = {
          id = 1010;
          home = "/usr/alice";
        };
        project = {
          id = 1012;
          leader = "alice";
          members = [ "alice" ];
        };
      };
    }
  );
  updatedCpu =
    (make { machines.build.configuration.files."user-workflow" = "updated\n"; }).systems.build;
  conflicting = (make ({ lib, ... }: { users.alice.id = lib.mkForce 1014; })).systems.files;
  occupied = (make { users.eve.id = 1; }).systems.files;
  unknownMember = (make { users.project.members = [ "missing" ]; }).systems.files;
  blockedDirectory =
    (make {
      users.carol.id = 1013;
      machines.files.configuration.services.cwfs.directories."/projects/plain" = {
        owner = "alice";
        group = "project";
      };
    }).systems.files;
  missingKey =
    (make { machines.auth.configuration.services.auth.requiredUsers = [ "missing" ]; }).systems.auth;
  emptyKey =
    (make { machines.auth.configuration.services.auth.requiredUsers = [ "empty" ]; }).systems.auth;
}
