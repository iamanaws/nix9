{
  recoveryName ? "shared-recovery",
}:
let
  pkgs = import <nix9>;
  identity =
    name:
    pkgs.mkDerivation {
      inherit name;
      protectedPackage = pkgs.rc;
      buildCommand = ''
        ~ `{cat /dev/user} none || exit 'wrong builder identity'
        test ! -w /usr/local/nix/state/db/db.sqlite || exit 'builder can write store database'
        test ! -r /adm/shared.keys || exit 'builder can read service credentials'
        if(rc -c 'echo damaged >> $protectedPackage/bin/rc' >[2]/dev/null)
          exit 'builder can modify an existing package'
        mkdir -p $out/private
        echo private-output > $out/private/result
        chmod 600 $out/private/result
        chmod 700 $out/private
        cat /dev/user > $out/identity
      '';
    };
  environment =
    version:
    pkgs.buildEnv {
      name = "shared-environment-${version}";
      paths = [
        (pkgs.mkDerivation {
          name = "shared-choice-${version}";
          buildCommand = ''
            mkdir -p $out/bin
            echo '#!/bin/rc' > $out/bin/shared-choice
            echo 'echo ${version}' >> $out/bin/shared-choice
            chmod 555 $out/bin/shared-choice
          '';
        })
      ];
    };
in
{
  envOne = environment "one";
  envTwo = environment "two";
  one = identity "shared-one";
  two = identity "shared-two";
  recovery = identity recoveryName;
  queued = [
    (identity "${recoveryName}-queued-one")
    (identity "${recoveryName}-queued-two")
  ];
  largeInput = pkgs.mkDerivation {
    name = "shared-large-input";
    passAsFile = [ "message" ];
    message = builtins.concatStringsSep "" (builtins.genList (_: "data") 16384);
    buildCommand = ''
      cat $messagePath > $out
    '';
  };
  detached = pkgs.mkDerivation {
    name = "shared-detached";
    probeSource = ./shared-detached.c;
    buildCommand = ''
      6c -o probe.6 $probeSource
      6l -o probe probe.6
      mkdir $out
      ./probe $out
    '';
  };
  failure = pkgs.mkDerivation {
    name = "shared-failure";
    buildCommand = ''
      echo 'intentional shared build failure' >[1=2]
      exit 'failure'
    '';
  };
  timeout = pkgs.mkDerivation {
    name = "shared-timeout";
    delaySource = ./remote-delay.c;
    buildCommand = ''
      6c -o delay.6 $delaySource
      6l -o delay delay.6
      echo SHARED-WAITING >[1=2]
      ./delay 60
      echo unexpected > $out
    '';
  };
}
