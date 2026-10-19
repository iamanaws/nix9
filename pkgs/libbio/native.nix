{ mkDerivation, src }:
mkDerivation {
  name = "libbio";
  inherit src;
  buildPhase = "mk 'LIB=libbio.a'";
  installPhase = ''
    mkdir -p $out/lib
    cp libbio.a $out/lib/
  '';
}
