{ mkDerivation, src }:
mkDerivation {
  name = "libdisk";
  inherit src;
  buildFlags = [ "libdisk.a" ];
  makeFlags = [ "LIB=libdisk.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libdisk.a $out/lib/
  '';
}
