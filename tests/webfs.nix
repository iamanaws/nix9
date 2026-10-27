{ packages }:
let
  pkgs = import packages;
  library = pkgs.stdenv.mkDerivation {
    name = "cache-answer";
    buildCommand = "echo 42 > $out";
  };
in
pkgs.stdenv.mkDerivation {
  name = "cache-program";
  inherit library;
  buildCommand = ''
    mkdir -p $out/bin
    echo '#!/bin/rc
    cat '^$library^'
    ' > $out/bin/answer
    chmod +x $out/bin/answer
  '';
}
