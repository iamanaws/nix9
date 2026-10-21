let
  pkgs = import <nix9>;
in
pkgs.buildEnv {
  name = "ramfs-environment";
  paths = [ pkgs.ramfs ];
}
