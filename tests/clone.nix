{ packages, url }:
let
  pkgs = import packages;
  clone = pkgs.clone.override {
    fetchgit = args: pkgs.fetchgit (args // { inherit url; });
  };
in
{
  inherit clone;
  environment = pkgs.buildEnv {
    name = "copy-session";
    paths = [
      clone
      pkgs.ramfs
    ];
    namespace = "ramfs -m /mnt";
  };
}
