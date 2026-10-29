let
  pkgs = import <nix9>;
  data = pkgs.mkDerivation {
    name = "prebuilt-retained-data";
    buildCommand = "echo retained-data > $out";
  };
  command =
    version:
    pkgs.mkDerivation {
      name = "prebuilt-command-${version}";
      buildCommand = ''
        mkdir -p $out/bin
        echo '#!/bin/rc
        echo ${version}' > $out/bin/prebuilt-version
        chmod 755 $out/bin/prebuilt-version
      '';
    };
  installation =
    version: extra:
    pkgs.mkInstallation {
      imports = [
        {
          name = "prebuilt";
          machines = {
            builder = {
              ip = "10.0.2.100";
              configuration = {
                services.ndb.dns.enable = false;
                files.version = "builder\n";
              };
            };
            target = {
              ip = "10.0.2.101";
              hostName = "target-${version}";
              configuration = {
                services.ndb.dns.enable = false;
                logging.enable = true;
                logging.files.prebuilt.mode = if version == "one" then "0640" else "0600";
                packages = [ (command version) ];
                files = {
                  version = version + "\n";
                  dependency = "${data}\n";
                };
              };
            };
          };
        }
        extra
      ];
    };
  one = (installation "one" { }).systems.target;
  fixtures = {
    inherit one data;
    two = (installation "two" { }).systems.target;
    wrong = (installation "one" { }).systems.builder;
    notSystem = pkgs.buildEnv { };
    unsupported = one.overrideAttrs (old: {
      name = "prebuilt-unsupported";
      buildCommand = old.buildCommand + "\necho unsupported > $out/system\n";
    });
    incomplete = one.overrideAttrs (old: {
      name = "prebuilt-incomplete";
      buildCommand = old.buildCommand + "\nrm $out/hostName\n";
    });
    failedActivation = one.overrideAttrs (old: {
      name = "prebuilt-failed-activation";
      buildCommand = old.buildCommand + "\necho 'exit prebuilt-fixture-failed' > $out/activate\n";
    });
    needsRuntime =
      (installation "one" (
        { lib, ... }: {
          machines.target.configuration.services.ndb.include = lib.mkForce [ "/tmp/prebuilt-site.ndb" ];
        }
      )).systems.target;
  };
in
fixtures
// {
  bundle = pkgs.mkDerivation {
    name = "prebuilt-transfer-fixtures";
    buildCommand = ''
      mkdir -p $out
      ${pkgs.lib.concatStringsSep "\n" (
        pkgs.lib.mapAttrsToList (name: path: ''
          echo ${path} > $out/${name}
        '') fixtures
      )}
    '';
  };
}
