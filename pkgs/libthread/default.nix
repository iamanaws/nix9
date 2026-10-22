{ mkDerivation, src }:
mkDerivation {
  name = "libthread";
  inherit src;
  buildFlags = [ "libthread.a" ];
  makeFlags = [ "LIB=libthread.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libthread.a $out/lib/
  '';
}
