{
  lib,
  runCommand,
  fetchurl,
  callPackage,
}:
let
  version = "2.34.8";
  source = fetchurl {
    url = "https://github.com/NixOS/nix/archive/refs/tags/${version}.tar.gz";
    hash = "sha256:ecc2f226a1ba27ad56eb85f42af8f078067fe5a219fceb82cb3fda9ba24387a5";
  };
  cc9 = callPackage ../cc9 { };
  dependencies = callPackage ../cc9-libs { inherit cc9; };
  libraries = callPackage ./libraries.nix {
    inherit
      source
      version
      cc9
      dependencies
      ;
  };
in
runCommand "nix-${version}"
  {
    passthru = {
      inherit
        source
        cc9
        version
        dependencies
        libraries
        ;
    };
    meta = {
      description = "Experimental native Nix store and evaluator for 9front";
      license = lib.licenses.lgpl21Plus;
    };
  }
  ''
    mkdir -p "$out"
    cp ${libraries}/meson-build/cli/nix-{store,instantiate,build}.elf "$out/"
  ''
