{ packages, compressed }:
let
  pkgs = import packages;
  commands = pkgs.buildTools.commands ++ [
    "awk"
    "grep"
    "gunzip"
  ];
in
pkgs.stdenv.mkDerivation {
  name = "build-tools-tests";
  inherit compressed;
  buildTools = pkgs.buildTools;
  checkScript = ./build-tools.rc;
  buildCommand = ''
    for(command in ${builtins.concatStringsSep " " commands}) {
      test `{whatis $command} '=' $buildTools/bin/$command
    }
    mkdir hidden
    bind hidden /amd64/bin
    bind hidden /rc/bin
    workRoot=`{pwd}
    . $checkScript $compressed
    echo passed > $out
  '';
}
