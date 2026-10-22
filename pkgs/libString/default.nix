{ mkDerivation, src }:
mkDerivation {
  name = "libString";
  inherit src;
  makeFlags = [ "LIB=libString.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libString.a $out/lib/
  '';
}
