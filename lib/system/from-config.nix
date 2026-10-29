{
  mkDerivation,
  buildEnv,
  lib,
  packages,
}:
evaluated:
let
  failures = map (check: check.message) (
    builtins.filter (check: !check.assertion) evaluated.assertions
  );
  build = import ./build.nix {
    inherit mkDerivation buildEnv lib;
    ndbPackage = packages.ndb;
    authPackage = packages.auth;
    cpuPackage = packages.rcpu;
    listenPackage = packages.listen;
    exportfsPackage = packages.exportfs;
    namespaceTools = packages.namespaceTools;
  };
in
if failures != [ ] then
  throw ("mkSystem: " + builtins.concatStringsSep "; " failures)
else
  lib.showWarnings evaluated.warnings (
    build (builtins.intersectAttrs (builtins.functionArgs build) evaluated)
  )
