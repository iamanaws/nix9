{
  pkgs ? import <nix9>,
}:
let
  remotePayload = builtins.toFile "remote-input" "input created on the terminal\n";
  delay = pkgs.mkDerivation {
    name = "remote-test-delay";
    src = ./delay.c;
    buildCommand = ''
      mkdir -p $out/bin
      6c -o sleep.6 $src
      6l -o $out/bin/remote-test-sleep sleep.6
    '';
  };
  project =
    name: command:
    pkgs.mkDerivation {
      inherit name remotePayload;
      nativeBuildInputs = [ delay ];
      src = ./hello.c;
      buildCommand = ''
        echo remote-log-${name}
        mkdir -p $out/bin
        echo `{cat /dev/sysname} > $out/builder
        echo $remotePayload > $out/input-path
        cp $remotePayload $out/input
        ${command}
      '';
    };
in
{
  hello = project "remote-hello" ''
    6c -o hello.6 $src
    6l -o $out/bin/hello hello.6
  '';
  parallelOne = project "remote-parallel-one" "remote-test-sleep 3";
  parallelTwo = project "remote-parallel-two" "remote-test-sleep 3";
  pooledOne = project "remote-pooled-one" ''
    echo ready > /tmp/nix9-parallel-one
    while(! test -e /tmp/nix9-parallel-two) remote-test-sleep 1
    status='''
  '';
  pooledTwo = project "remote-pooled-two" ''
    echo ready > /tmp/nix9-parallel-two
    while(! test -e /tmp/nix9-parallel-one) remote-test-sleep 1
    status='''
  '';
  batch = (project "remote-batch" "status=''").overrideAttrs (_: {
    requiredSystemFeatures = [ "batch" ];
  });
  failing = project "remote-failing" "echo remote-intentional-failure >[1=2]; exit failed";
  cancel = project "remote-cancel" ''
    echo $pid > /tmp/nix9-remote-cancel-pid
    remote-test-sleep 600
    echo remote-cancel-leaked > /tmp/nix9-remote-cancel-leaked
  '';
  afterCancel = project "remote-after-cancel" "status=''";
  failover = project "remote-failover" "status=''";
  unavailable = project "remote-unavailable" "status=''";
  denied = project "remote-denied" "status=''";
  localBuild = project "remote-local-override" "status=''";
}
