{ mkDerivation, src }:
mkDerivation {
  name = "libregexp";
  inherit src;
  makeFlags = [ "LIB=libregexp.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libregexp.a $out/lib/
  '';
}
