let
  pkgs = import <nix9>;
  fixture = import ./cpu-fixture.nix;
  command =
    version:
    pkgs.mkDerivation {
      name = "cpu-choice-${version}";
      buildCommand = ''
        mkdir -p $out/bin
        echo '#!/bin/rc
        echo ${version}' > $out/bin/cpu-choice
        chmod +x $out/bin/cpu-choice
      '';
    };
  system =
    version: timesync: networking:
    pkgs.mkSystem {
      hostName = "nix9-cpu";
      packages = [ (command version) ];
      files.version = "${version}\n";
      webfs.certificatePins."cpu.invalid" = [
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      ];
      networking = {
        enable = true;
      }
      // networking;
      logging.enable = true;
      services = {
        webfs.enable = true;
        inherit timesync;
      };
    };
  rtc = {
    enable = true;
    logging = true;
  };
  legacy = system "legacy" rtc { };
in
{
  # Exercise upgrading from a retained generation built before CPU hooks existed.
  legacy = legacy.overrideAttrs (old: {
    name = "nix9-cpu-legacy";
    buildCommand = old.buildCommand + "\nrm $out/hooks/cpurc.local\n";
  });
  one = system "one" rtc { };
  two =
    system "two"
      {
        enable = true;
        source = "ntp";
        server = "10.0.2.2";
        port = fixture.port;
        logging = true;
      }
      {
        useDHCP = false;
        address = "10.0.2.42";
        prefixLength = 24;
        defaultGateway = "10.0.2.2";
        nameservers = [ "10.0.2.3" ];
      };
  unmanaged = system "unmanaged" { } { };
}
