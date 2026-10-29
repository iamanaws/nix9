let
  pkgs = import <nix9>;
  fixture = import ./listen-fixture.nix;
  command =
    version:
    pkgs.mkDerivation {
      name = "listen-command-${version}";
      buildCommand = ''
        mkdir -p $out/bin
        echo '#!/bin/rc
        echo ${version}' > $out/bin/listen-choice
        chmod 755 $out/bin/listen-choice
      '';
    };
  script = ''
    while() {
      request=`{read}
      if(~ $#request 0) exit '''
      switch($request) {
      case snapshot
        listen-choice
        cat /cfg/nix9/files/version
        echo $user
        echo $nix9System
        echo $nix9WebfsSystem
        echo $*
        hget http://10.0.2.2:${toString fixture.port}/payload
        echo LISTEN-END
      case quit
        exit '''
      }
    }
  '';
  enabled = {
    enable = true;
    tcp."17010" = script;
    tcp."17012" = "echo EXTRA-SERVICE\necho LISTEN-END\n";
  };
  system =
    version: listen:
    pkgs.mkSystem {
      hostName = "nix9-listen";
      packages = [ (command version) ];
      files.version = "${version}\n";
      networking.enable = true;
      logging.enable = true;
      services = {
        inherit listen;
        timesync.enable = true;
        webfs.enable = true;
      };
    };
in
{
  one = system "one" enabled;
  two = system "two" (enabled // { tcp."17010" = script; });
  disabled = system "disabled" { };
  empty = system "empty" { enable = true; };
  baseline = system "baseline" { };
  invalidEnable = system "invalid" { enable = 1; };
  invalidTCP = system "invalid" {
    enable = true;
    tcp = [ ];
  };
  invalidZero = system "invalid" {
    enable = true;
    tcp."0" = script;
  };
  invalidHigh = system "invalid" {
    enable = true;
    tcp."65536" = script;
  };
  invalidLeadingZero = system "invalid" {
    enable = true;
    tcp."017010" = script;
  };
  invalidName = system "invalid" {
    enable = true;
    tcp."../17010" = script;
  };
  invalidOption = system "invalid" {
    enable = true;
    tcp."-1" = script;
  };
  invalidScript = system "invalid" {
    enable = true;
    tcp."17010" = 1;
  };
  invalidEmptyScript = system "invalid" {
    enable = true;
    tcp."17010" = " \n\t";
  };
  disabledScripts = system "invalid" { tcp."17010" = script; };
}
