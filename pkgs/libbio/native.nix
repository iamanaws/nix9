{ mkDerivation, src }:
mkDerivation {
  name = "libbio";
  inherit src;
  buildCommand = ''
    units=`{$tools/bin/awk '/\.\$O/ { sub(/\.\$O.*/, ""); print }' $src/mkfile}
    for(unit in $units) {
      $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -o $unit.6 $src/$unit.c
    }
    $tools/bin/mkdir -p $out/lib
    $tools/bin/ar rc $out/lib/libbio.a *.6
  '';
}
