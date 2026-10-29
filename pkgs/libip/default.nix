{ mkDerivation, src }:
mkDerivation {
  name = "libip";
  inherit src;
  makeFlags = [ "LIB=libip.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libip.a $out/lib/
  '';
}
