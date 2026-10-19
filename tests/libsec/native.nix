{ packages }:
let
  pkgs = import packages;
  tests = "sha2 hmac chacha aesgcm eg mp";
in
pkgs.stdenv.mkDerivation {
  name = "crypto-tests";
  src = pkgs.libsec.src;
  mpTest = ./mp.c;
  sourceRoot = "source/sys/src/libsec/test";
  buildInputs = [
    pkgs.libsec
    pkgs.libmp
  ];
  postUnpack = "cp $mpTest mp.c";
  buildPhase = ''
    for(test in ${tests}) {
      6c -I../../libmp/port -o $test.6 $test.c
      6l -o $test $test.6
    }
  '';
  doCheck = true;
  checkPhase = "for(test in ${tests}) ./$test";
  installPhase = "echo passed > $out";
}
