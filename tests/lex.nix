{ packages }:
let
  pkgs = import packages;
  parser = pkgs.stdenv.mkDerivation {
    name = "lex-parser";
    src = ./lex;
    nativeBuildInputs = [
      pkgs.lex
      pkgs.yacc
    ];
    buildInputs = [ pkgs.libl ];
    doCheck = true;
    checkPhase = "test `{echo '20 + 22' | ./6.out} '=' 42";
  };
in
{
  inherit parser;
  invalid = parser.overrideAttrs { preBuild = "echo '%%\n[abc { return 0; }\n%%' > scanner.l"; };
  shell = pkgs.mkShell { inputsFrom = [ parser ]; };
}
