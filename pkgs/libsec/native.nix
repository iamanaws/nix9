{ mkDerivation, src }:
mkDerivation {
  name = "libsec";
  inherit src;
  buildCommand = ''
    $tools/bin/mkdir objects
    for(unit in secp256r1 secp384r1 secp256k1 jacobian) {
      $tools/bin/echo '#include "os.h"' > $unit.c
      $tools/bin/echo '#include <mp.h>' >> $unit.c
      $tools/bin/mpc $src/sys/src/libsec/port/$unit.mp >> $unit.c
    }
    units=`{$tools/bin/awk '
      /^CFILES *=/ { sub(/^CFILES *=/, ""); active=1 }
      active && NF==0 { exit }
      active { gsub(/\\/, ""); gsub(/\.c/, ""); print }
    ' $src/sys/src/libsec/port/mkfile}
    for(unit in $units) {
      if(! $tools/bin/test -f $src/sys/src/libsec/amd64/$unit.s) {
        file=$src/sys/src/libsec/port/$unit.c
        if($tools/bin/test -f $unit.c) file=$unit.c
        $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -I $src/sys/src/libmp/port -I $src/sys/src/libsec/port -o objects/$unit.6 $file
      }
    }
    for(unit in `{$tools/bin/awk '/\.\$O/ { sub(/\.\$O.*/, ""); print }' $src/sys/src/libsec/amd64/mkfile}) {
      $tools/bin/6a -I $tools/amd64/include -I $tools/sys/include -o objects/$unit.6 $src/sys/src/libsec/amd64/$unit.s
    }
    $tools/bin/mkdir -p $out/lib
    $tools/bin/ar rc $out/lib/libsec.a objects/*.6
  '';
}
