let
  pkgs = import <nix9>;
in
pkgs.buildEnv {
  paths = [ (import ./default.nix { inherit pkgs; }) ];
}
