{
  mkDerivation,
  src,
  buildPackages,
  libbio,
}:
mkDerivation {
  name = "awk-maketab";
  inherit src;
  nativeBuildInputs = [ buildPackages.yacc ];
  buildInputs = [ libbio ];
  buildPhase = ''
    yacc -d -o awkgram.c awkgram.y
    6c maketab.c
    6l -o maketab maketab.6
  '';
  installPhase = ''
    mkdir -p $out/bin
    cp maketab $out/bin/
  '';
}
