let
  pkgs = import <nix9>;
in
pkgs.mkDerivation {
  name = "shared-project";
  src = ./.;
}
