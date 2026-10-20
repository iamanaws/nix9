{ packages }:
let
  pkgs = import packages;
  parser = pkgs.stdenv.mkDerivation {
    name = "yacc-parser";
    src = ./yacc;
    nativeBuildInputs = [ pkgs.yacc ];
    doCheck = true;
    checkPhase = "./6.out '20+22'";
  };
in
{
  inherit parser;
  invalid = parser.overrideAttrs { preBuild = "echo invalid > parser.y"; };
  shell = pkgs.mkShell { inputsFrom = [ parser ]; };
}
