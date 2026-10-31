{
  pkgs ? import <nix9>,
}:
let
  base = import <nix9/examples/netroot/configuration.nix>;
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        base
        ({ lib, ... }: {
          machines.batch = {
            ip = "10.0.2.103";
            boot.provider = "files";
            boot.root = "stable";
            configuration = {
              imports = [ base.machines.build.configuration ];
              networking.interfaces.ether0.address = lib.mkForce "10.0.2.103";
              services.cpu.keyPattern = lib.mkForce "dom=nix9.netroot user=batch";
            };
          };
          machines.build.configuration.files.version = "one\n";
          roots.stable.files."network-root-marker" = "root-one\n";
          roots.stable.files."sys/lib/tls/webfs/revoked" = "";
          machines.build.configuration.services.listen = {
            enable = true;
            tcp."17024" =
              "echo $user; test ! -r /adm/cpu.keys && echo keys-protected; cat /cfg/nix9/files/version\n";
          };
          machines.batch.configuration.files.version = "batch\n";
          machines.auth.configuration.services.ndb.dns.enable = false;
          machines.auth.configuration.services.auth.speaksFor.batch = [ "glenda" ];
          machines.files.configuration.services.ndb.dns.enable = false;
          machines.files.configuration.services.cwfs.deviceMap = lib.mkForce {
            w0 = "/dev/sdG0/data";
            w1 = "/dev/sdH0/data";
          };
          machines.build.configuration.services.ndb.dns.enable = false;
          machines.batch.configuration.services.ndb.dns.enable = false;
        })
        extra
      ];
    };
  first = make { };
in
{
  inherit first;
  second = make (
    { lib, ... }: {
      machines.build.configuration.files.version = lib.mkForce "two\n";
      machines.build.hostName = "worker";
      roots.next.files."network-root-marker" = "root-two\n";
      machines.build.boot.root = lib.mkForce "next";
    }
  );
  renamed = make {
    machines.build.machineId = "builder-id";
    machines.build.hostName = "worker";
  };
  invalid = {
    unknownProvider = make { machines.build.boot.provider = "missing"; };
    selfProvider = make { machines.build.boot.provider = "build"; };
    disabledProvider = make (
      { lib, ... }: { machines.files.configuration.services.cwfs = lib.mkForce { enable = false; }; }
    );
    wrongPort = make { machines.files.configuration.services.cwfs.port = 565; };
    missingAuth = make ({ lib, ... }: { defaults.auth = lib.mkForce null; });
    missingDomain = make ({ lib, ... }: { defaults.authdom = lib.mkForce null; });
    bootedAuth = make { machines.auth.boot.provider = "files"; };
    bootedProvider = make { machines.files.boot.provider = "auth"; };
    noCpu = make (
      { lib, ... }: { machines.build.configuration.services.cpu = lib.mkForce { enable = false; }; }
    );
    dhcp = make (
      { lib, ... }: {
        machines.build.configuration.networking.interfaces.ether0 = lib.mkForce { useDHCP = true; };
      }
    );
    addressMismatch = make (
      { lib, ... }: {
        machines.build.configuration.networking.interfaces.ether0.address = lib.mkForce "10.0.2.104";
      }
    );
    unknownRoot = make { machines.build.boot.root = "missing"; };
    longIdentity = make { machines.build.machineId = "builder-with-a-long-machine-id"; };
    relativeFile = make { roots.stable.files."../root" = "invalid"; };
    absoluteFile = make { roots.stable.files."/root" = "invalid"; };
    nestedFiles = make {
      roots.stable.files = {
        probe = "invalid";
        "probe/child" = "invalid";
      };
    };
    managedNamespace = make { roots.stable.files."lib/namespace.local" = "invalid"; };
    managedBoot = make { roots.stable.files."cfg/nix9/boot/build/init" = "invalid"; };
    rootState = make { machines.build.boot.stateDirectory = "/systems"; };
    sharedState = make { machines.batch.boot.stateDirectory = "/machines/build"; };
    nestedState = make { machines.batch.boot.stateDirectory = "/machines/build/batch"; };
    unknownOption = make { machines.build.boot.reboot = true; };
  };
}
