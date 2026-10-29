let
  pkgs = import <nix9>;
  fixture = import ./rcpu-fixture.nix;
  command =
    version:
    pkgs.mkDerivation {
      name = "rcpu-command-${version}";
      buildCommand = ''
        mkdir -p $out/bin
        echo '#!/bin/rc
        echo ${version}' > $out/bin/rcpu-choice
        echo '#!/bin/rc -e
        echo RCPU-BEGIN
        echo $user
        echo `{cat /dev/sysname}
        echo $service
        rcpu-choice
        cat /cfg/nix9/files/version
        echo $nix9System
        echo $nix9WebfsSystem
        cat /sys/lib/tls/webfs/hosts/rcpu.invalid
        hget http://10.0.2.2:${toString fixture.port}/payload
        echo RCPU-END' > $out/bin/rcpu-snapshot
        echo '#!/bin/rc -e
        while() {
          request=`{read}
          if(~ $#request 0 || ~ $request quit) exit
          if(~ $request snapshot) rcpu-snapshot
        }' > $out/bin/rcpu-session
        chmod 755 $out/bin/*
      '';
    };
  system =
    version: pin: extra:
    pkgs.mkSystem {
      imports = [ extra ];
      hostName = "nix9-rcpu";
      packages = [ (command version) ];
      files.version = "${version}\n";
      webfs.certificatePins."rcpu.invalid" = [ pin ];
      networking.enable = true;
      logging.enable = true;
      logging.files.auth.mode = "0660";
      services = {
        auth = {
          enable = true;
          speaksFor.terminal = if version == "one" then [ "glenda" ] else [ ];
        };
        cpu = {
          enable = true;
          allowedUsers = [ "glenda" ];
          keyFile = "/adm/rcpu-host.keys";
          keyPattern = "dom=nix9.test user=rcpuhost";
        };
        timesync.enable = true;
        webfs.enable = true;
        listen = {
          enable = true;
          tcp."17010" = "echo RCPU-LISTENER-COEXISTENCE\n";
        };
      };
    };
in
{
  one = system "one" "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" { };
  two = system "two" "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" { };
  denied = system "denied" "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" (
    { lib, ... }: {
      services.cpu.allowedUsers = lib.mkForce [ "nobody" ];
    }
  );
  disabled = system "disabled" "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" (
    { lib, ... }: {
      services.auth = {
        enable = lib.mkForce false;
        speaksFor = lib.mkForce { };
      };
      services.cpu = {
        enable = lib.mkForce false;
        allowedUsers = lib.mkForce [ ];
        keyFile = lib.mkForce null;
        keyPattern = lib.mkForce "";
      };
    }
  );
}
