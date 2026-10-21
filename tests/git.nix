{
  packages,
  url,
  rev,
  hash,
}:
let
  pkgs = import packages;
  source = pkgs.fetchgit { inherit url rev hash; };
in
{
  inherit source;
  hello = pkgs.mkDerivation {
    name = "git-hello";
    src = source;
    buildPhase = ''
      6c -o main.6 main.c
      6l -o hello main.6
    '';
    installPhase = ''
      mkdir -p $out/bin
      cp hello $out/bin/hello
    '';
  };
}
