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
  failures = map (check: check.message) (
    builtins.filter (check: !check.assertion) evaluated.assertions
  );
  build = import ./build.nix {
    inherit mkDerivation buildEnv;
    ndbPackage = packages.ndb;
  };
in
if failures != [ ] then
  throw ("mkSystem: " + builtins.concatStringsSep "; " failures)
else
  lib.showWarnings evaluated.warnings (
    build (builtins.intersectAttrs (builtins.functionArgs build) evaluated)
  )
