{
  pkgs ? import /usr/local/pkg/native-packages,
}:
pkgs.mkDerivation {
  name = "hello";
  src = ./hello.c;
  buildCommand = ''
    6c -o hello.6 $src
    mkdir -p $out/bin
    6l -s -o $out/bin/hello hello.6
  '';
}
