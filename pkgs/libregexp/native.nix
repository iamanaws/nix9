{ mkDerivation, src }:
mkDerivation {
  name = "libregexp";
  inherit src;
  buildPhase = "mk 'LIB=libregexp.a'";
  installPhase = ''
    mkdir -p $out/lib
    cp libregexp.a $out/lib/
  '';
}
