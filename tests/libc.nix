{ packages }:
let
  pkgs = import packages;
  shadow = pkgs.stdenv.mkDerivation {
    name = "shadow-libc";
    buildCommand = ''
      mkdir -p $out/lib
      echo invalid-library > $out/lib/libc.a
    '';
  };
  program = pkgs.stdenv.mkDerivation {
    name = "libc-tests";
    src = ./libc.c;
    inherit (pkgs) libc;
    libcSource = pkgs.libc.src;
    nativeBuildInputs = [ pkgs.sha1sum ];
    buildInputs = [
      pkgs.libc
      shadow
    ];
    buildCommand = ''
      test `{sha1sum < /amd64/lib/libc.a} '=' `{sha1sum < $libc/lib/libc.a}
      mkdir -p $out/bin
      cp $src main.c
      6c -o main.6 main.c
      6l -o $out/bin/libc-test main.6
      $out/bin/libc-test
      for(name in strchr pow) {
        cp $libcSource/test/$name.c $name.c
        6c -o $name.6 $name.c
        6l -o $out/bin/$name $name.6
        $out/bin/$name
      }
    '';
  };
in
{
  inherit program;
  shell = pkgs.mkShell {
    inputsFrom = [ program ];
    shellHook = ''
      test `{sha1sum < /amd64/lib/libc.a} '=' `{sha1sum < ${pkgs.libc}/lib/libc.a}
    '';
  };
}
