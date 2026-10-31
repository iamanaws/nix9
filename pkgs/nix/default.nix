{
  lib,
  runCommand,
  fetchurl,
  callPackage,
  meson,
  ninja,
  pkg-config,
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
    nativeBuildInputs = [
      meson
      ninja
      pkg-config
    ];
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
    mkdir commands
    cp -R ${libraries}/nix-${version}/src commands/src
    chmod -R u+w commands
    cd commands
    patch -p1 < ${./patches/nix-build.patch}
    cp ${./meson.build} meson.build
    cp ${./main.cc} main.cc
    cp ${./shell.cc} shell.cc
    export PKG_CONFIG_LIBDIR=${libraries}/lib/pkgconfig
    meson setup build --cross-file ${libraries}/cross.ini \
      --wrap-mode=nofallback -Dbuildtype=plain -Doptimization=2
    ninja -C build -j "$NIX_BUILD_CORES"
    mkdir -p "$out"
    cp build/nix-{store,instantiate,build,build-remote}.elf "$out/"
  ''
