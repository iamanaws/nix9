{
  packages,
  url,
  hash,
}:
let
  pkgs = import packages;
  source = pkgs.fetchurl {
    inherit url hash;
    name = "hello.c";
  };
in
{
  inherit source;
  hello = pkgs.mkDerivation {
    name = "fetched-hello";
    src = source;
    buildCommand = ''
      $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -o hello.6 $src
      $tools/bin/6l -l -E _main -o $out hello.6 $tools/amd64/lib/libc.a
    '';
  };
}
