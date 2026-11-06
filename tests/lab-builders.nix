{
  label,
  pkgs ? import <nix9>,
}:
let
  package = pkgs.mkDerivation {
    name = "lab-remote-${label}";
    src = /n/projects/hello/hello.c;
    buildCommand = ''
      ~ `{cat /dev/user} none || exit 'wrong build identity'
      test ! -r /adm/cpu.keys || exit 'builder can read CPU credentials'
      test ! -r /adm/builder.keys || exit 'builder can read client credentials'
      mkdir -p $out/bin
      6c -o hello.6 $src
      6l -o $out/bin/hello hello.6
      echo `{cat /dev/sysname} > $out/builder
      echo `{cat /dev/user} > $out/identity
    '';
  };
in
{
  inherit package;
  environment = pkgs.buildEnv {
    name = "lab-remote-environment-${label}";
    paths = [ package ];
  };
}
