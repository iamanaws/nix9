{
  pkgs ? import <nix9>,
}:
pkgs.mkDerivation {
  name = "workstation-hello";
  src = ./hello.c;
  buildCommand = ''
    mkdir -p $out/bin
    6c -o hello.6 $src
    6l -o $out/bin/hello hello.6
    echo `{cat /dev/sysname} > $out/builder
  '';
}
