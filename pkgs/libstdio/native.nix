{ mkDerivation, src }:
mkDerivation {
  name = "libstdio";
  inherit src;
  makeFlags = [ "LIB=libstdio.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libstdio.a $out/lib/
  '';
}
