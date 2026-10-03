{ mkDerivation }:
let
  library = mkDerivation {
    name = "c-abi-library";
    src = ./callee.c;
    header = ./abi.h;
    buildCommand = ''
      $tools/bin/mkdir -p $out/lib $out/include
      $tools/bin/cp $header $out/include/abi.h
      $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -I $out/include -o callee.6 $src
      $tools/bin/ar rc $out/lib/libabi.a callee.6
    '';
  };
in
mkDerivation {
  name = "c-abi";
  inherit library;
  src = ./main.c;
  buildCommand = ''
    $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -I $library/include -o main.6 $src
    $tools/bin/mkdir -p $out/bin
    $tools/bin/6l -l -E _main -o $out/bin/abi-tests main.6 $library/lib/libabi.a $tools/amd64/lib/libc.a
  '';
}
