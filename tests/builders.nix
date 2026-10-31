{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/builders/configuration.nix>
        {
          machines.auth.configuration.services.ndb.dns.enable = false;
          machines.build.configuration.services.ndb.dns.enable = false;
          machines.terminal.configuration.services.ndb.dns.enable = false;
        }
        extra
      ];
    };
  initial = make { };
  system =
    extra:
    pkgs.mkSystem {
      imports = [ extra ];
      hostName = "terminal";
    };
in
{
  inherit initial;
  second = make {
    machines.batch = {
      ip = "10.0.2.103";
      configuration.networking.enable = true;
      configuration.services.ndb.dns.enable = false;
      configuration.nix.systemFeatures = [ "batch" ];
      configuration.services.cpu = {
        enable = true;
        allowedUsers = [ "glenda" ];
        keyFile = "/adm/cpu.keys";
        keyPattern = "dom=nix9.builders";
      };
    };
    machines.terminal.builders.batch = {
      user = "glenda";
      maxJobs = 1;
      supportedFeatures = [ "batch" ];
    };
    machines.terminal.builders.build.speedFactor = 2;
  };
  renamed = make { machines.build.hostName = "compile"; };
  standalone = system {
    nix.builders.build = {
      host = "cpu.example";
      keyPattern = "dom=example user=glenda";
    };
  };
  invalid = {
    unknown = (make { machines.terminal.builders.missing = { }; }).build;
    disabledCPU =
      (make ({ lib, ... }: { machines.build.configuration.services.cpu.enable = lib.mkForce false; }))
      .build;
    deniedUser = (make { machines.terminal.builders.build.user = "nobody"; }).build;
    overrideHost = (make { machines.terminal.configuration.nix.builders.build.host = "other"; }).build;
    zeroJobs = system {
      nix.builders.build = {
        host = "build";
        maxJobs = 0;
      };
    };
    invalidHost = system { nix.builders.build.host = "build; reboot"; };
    invalidUser = system {
      nix.builders.build = {
        host = "build";
        user = "user name";
      };
    };
    secret = system {
      nix.builders.build = {
        host = "build";
        keyPattern = "!password=secret";
      };
    };
    newline = system {
      nix.builders.build = {
        host = "build";
        keyPattern = "dom=test\n";
      };
    };
    negativeLocalJobs = system { nix.maxJobs = -1; };
    invalidFeature = system {
      nix.builders.build = {
        host = "build";
        supportedFeatures = [ "bad feature" ];
      };
    };
    noSystem = system {
      nix.builders.build = {
        host = "build";
        systems = [ ];
      };
    };
  };
}
