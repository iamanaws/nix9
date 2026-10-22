{ mkDerivation, src }:
mkDerivation {
  name = "libmp";
  inherit src;
  passthru.source = src;
  sourceRoot = "source/sys/src/libmp";
  makeFlags = [ "LIB=../libmp.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libmp.a $out/lib/
  '';
}
