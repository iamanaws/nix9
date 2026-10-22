{
  stdenv,
  src,
  buildPackages,
  libbio,
  libmp,
}:
stdenv.mkDerivation {
  name = "mpc";
  inherit src;
  sourceRoot = "source/sys/src/cmd";
  nativeBuildInputs = [ buildPackages.yacc ];
  buildInputs = [
    libbio
    libmp
  ];
  buildPhase = ''
    yacc mpc.y
    6c -o mpc.6 y.tab.c
    6l -o mpc mpc.6
  '';
  installPhase = ''
    mkdir -p $out/bin
    cp mpc $out/bin/mpc
  '';
}
