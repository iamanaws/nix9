{ mkDerivation, src }:
mkDerivation {
  name = "libsec";
  inherit src;
  sourceRoot = "source/sys/src/libsec";
  makeFlags = [ "LIB=../libsec.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libsec.a $out/lib/
  '';
}
