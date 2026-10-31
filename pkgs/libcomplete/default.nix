{ mkDerivation, src }:
mkDerivation {
  name = "libcomplete";
  inherit src;
  makeFlags = [ "LIB=libcomplete.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libcomplete.a $out/lib/
  '';
}
