{
  mkDerivation,
  buildEnv,
  lib,
  packages,
}:
configuration:
let
  evaluated =
    (import ./eval.nix {
      inherit lib;
      pkgs = packages;
    } configuration).config;
in
import ./from-config.nix {
  inherit
    mkDerivation
    buildEnv
    lib
    packages
    ;
} evaluated
