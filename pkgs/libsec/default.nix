{
  mkDerivation,
  src,
  buildPackages,
}:
mkDerivation {
  name = "libsec";
  inherit src;
  passthru.source = src;
  nativeBuildInputs = [ buildPackages.mpc ];
  sourceRoot = "source/sys/src/libsec";
  postUnpack = ''
    for(unit in secp256r1 secp384r1 secp256k1 jacobian) rm -f port/$unit.c
  '';
  makeFlags = [ "LIB=../libsec.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libsec.a $out/lib/
  '';
}
