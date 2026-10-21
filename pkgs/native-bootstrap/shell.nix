let
  pkgs = import ./packages;
in
pkgs.mkShell {
  nativeBuildInputs = [
    pkgs.yacc
    pkgs.lex
  ];
}
