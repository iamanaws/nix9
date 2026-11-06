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
      configuration.nix.settings.system-features = [ "batch" ];
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
    nix.distributedBuilds = true;
    nix.buildMachines = [
      {
        hostName = "cpu.example";
        keyPattern = "dom=example user=glenda";
      }
    ];
  };
  extended = make {
    machines.terminal.configuration.nix.buildMachines = [ { hostName = "external"; } ];
  };
  stopped = make { machines.terminal.configuration.nix.distributedBuilds = false; };
  singular = system {
    nix.buildMachines = [
      {
        hostName = "build";
        system = "x86_64-plan9";
        systems = [ ];
      }
    ];
  };
  invalid = {
    negativeTimeout = system {
      nix.buildMachines = [
        {
          hostName = "build";
          connectTimeout = -1;
        }
      ];
    };
    removedBuilders = system { nix.builders.build.host = "build"; };
    unknown = (make { machines.terminal.builders.missing = { }; }).build;
    disabledCPU =
      (make ({ lib, ... }: { machines.build.configuration.services.cpu.enable = lib.mkForce false; }))
      .build;
    deniedUser = (make { machines.terminal.builders.build.user = "nobody"; }).build;
    overrideHost =
      (make (
        { lib, ... }: {
          machines.terminal.configuration.nix.buildMachines = lib.mkForce [ { hostName = "other"; } ];
        }
      )).build;
    zeroJobs = system {
      nix.buildMachines = [
        {
          hostName = "build";
          maxJobs = 0;
        }
      ];
    };
    invalidHost = system { nix.buildMachines = [ { hostName = "build; reboot"; } ]; };
    invalidUser = system {
      nix.buildMachines = [
        {
          hostName = "build";
          user = "user name";
        }
      ];
    };
    secret = system {
      nix.buildMachines = [
        {
          hostName = "build";
          keyPattern = "!password=secret";
        }
      ];
    };
    newline = system {
      nix.buildMachines = [
        {
          hostName = "build";
          keyPattern = "dom=test\n";
        }
      ];
    };
    negativeLocalJobs = system { nix.settings.max-jobs = -1; };
    invalidFeature = system {
      nix.buildMachines = [
        {
          hostName = "build";
          supportedFeatures = [ "bad feature" ];
        }
      ];
    };
    noSystem = system {
      nix.buildMachines = [
        {
          hostName = "build";
          systems = [ ];
        }
      ];
    };
  };
}
