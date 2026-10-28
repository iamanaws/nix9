let
  pkgs = import <nix9>;
in
pkgs.stdenv.mkDerivation {
  name = "rcpu-hello";
  src = ./.;
}
