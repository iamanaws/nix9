{ packages }:
let
  pkgs = import packages;
  tests = "sha2 hmac chacha aesgcm eg mp";
in
pkgs.stdenv.mkDerivation {
  name = "crypto-tests";
  src = pkgs.libsec.src;
  mpTest = ./mp.c;
  generatedHashes = ./generated.sha256;
  mpcPackage = pkgs.mpc;
  sourceRoot = "source/sys/src/libsec/test";
  nativeBuildInputs = [
    pkgs.mpc
    pkgs.sha1sum
  ];
  buildInputs = [
    pkgs.libsec
    pkgs.libmp
  ];
  postUnpack = "cp $mpTest mp.c";
  buildPhase = ''
    test `{whatis mpc} '=' $mpcPackage/bin/mpc
    echo 'bases(a,b,c,d) { a=123; b=0x7b; c=0b1111011; d=0173; }' | mpc > bases.c
    for(name in a b c d) grep 'uitomp[(]123UL, '^$name^'[)];' bases.c
    for(unit in secp256r1 secp384r1 secp256k1 jacobian) {
      echo '#include "os.h"' > $unit.c
      echo '#include <mp.h>' >> $unit.c
      mpc ../port/$unit.mp >> $unit.c
      expected=`{awk -v 'name='$unit.c '$2 == name { print $1 }' $generatedHashes}
      test `{sha1sum -2 256 < $unit.c} '=' $expected
    }
    if(echo 'broken(' | mpc > /dev/null) exit 'invalid mpc input accepted'
    for(test in ${tests}) {
      6c -I../../libmp/port -o $test.6 $test.c
      6l -o $test $test.6
    }
  '';
  doCheck = true;
  checkPhase = "for(test in ${tests}) ./$test";
  installPhase = "echo passed > $out";
}
