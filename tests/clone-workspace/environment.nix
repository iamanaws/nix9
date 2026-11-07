let
  pkgs = import <nix9>;
in
pkgs.buildEnv {
  name = "clone-development";
  paths = [ (import ./default.nix { inherit pkgs; }) ];
}
