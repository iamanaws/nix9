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
      6c -o hello.6 $src
      6l -o $out hello.6
    '';
  };
}
