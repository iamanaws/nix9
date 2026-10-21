{ mkDerivation, src }:
mkDerivation {
  name = "libauth";
  inherit src;
  makeFlags = [ "LIB=libauth.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libauth.a $out/lib/
  '';
}
