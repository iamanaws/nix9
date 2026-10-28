let
  pkgs = import <nix9>;
  command =
    version:
    pkgs.mkDerivation {
      name = "system-command-${version}";
      buildCommand = ''
        mkdir -p $out/bin
        echo '#!/bin/rc
        echo ${version}' > $out/bin/nix9-system-choice
        cp $out/bin/nix9-system-choice $out/bin/nix9-${version}-only
        chmod +x $out/bin/*
      '';
    };
  data = pkgs.mkDerivation {
    name = "system-file-data";
    buildCommand = "echo retained > $out";
  };
  one = pkgs.mkSystem {
    hostName = "nix9";
    packages = [ (command "one") ];
    files = {
      message = "one's configuration\n";
      "nested/data" = "${data}\n";
      old = "old file\n";
    };
    webfs.certificatePins."example.invalid" = [
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ];
  };
in
{
  inherit one;
  notSystem = pkgs.buildEnv { };
  two = pkgs.mkSystem {
    hostName = "nix9-two";
    packages = [ (command "two") ];
    files.message = "two's configuration\n";
    webfs.certificatePins."second.invalid" = [
      "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    ];
  };
  invalidHost = pkgs.mkSystem { hostName = "../invalid"; };
  invalidFile = pkgs.mkSystem {
    hostName = "nix9";
    files."../escape" = "invalid";
  };
  conflictingFiles = pkgs.mkSystem {
    hostName = "nix9";
    files = {
      a = "file";
      "a/b" = "child";
    };
  };
  invalidPin = pkgs.mkSystem {
    hostName = "nix9";
    webfs.certificatePins."example.invalid" = [ "invalid" ];
  };
  invalidPinHost = pkgs.mkSystem {
    hostName = "nix9";
    webfs.certificatePins."../invalid" = [
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ];
  };
  collision = pkgs.mkSystem {
    hostName = "nix9";
    packages = [
      (command "one")
      (command "two")
    ];
  };
  failedActivation = one.overrideAttrs (old: {
    name = "system-failed-activation";
    buildCommand = old.buildCommand + ''
      echo 'exit activation-fixture-failed' > $out/activate
    '';
  });
}
