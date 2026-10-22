{ mkDerivation, src }:
mkDerivation {
  name = "libflate";
  inherit src;
  makeFlags = [ "LIB=libflate.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libflate.a $out/lib/
  '';
}
