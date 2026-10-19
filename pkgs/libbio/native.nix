{ mkDerivation, src }:
mkDerivation {
  name = "libbio";
  inherit src;
  makeFlags = [ "LIB=libbio.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libbio.a $out/lib/
  '';
}
