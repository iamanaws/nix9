{
  lib,
  runCommand,
  fetchurl,
  llvmPackages,
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
  inherit (dependencies) compression sodium sqlite;
  libraries = callPackage ./libraries.nix {
    inherit
      source
      version
      cc9
      dependencies
      ;
  };
in
runCommand "nix-util-${version}-9front-probe"
  {
    passthru = {
      inherit
        source
        cc9
        version
        compression
        sodium
        sqlite
        libraries
        ;
    };
    meta = {
      description = "Experimental native Nix store and evaluator for 9front";
      license = lib.licenses.lgpl21Plus;
    };
  }
  ''
    mkdir -p build "$out"
    nixSource=${libraries}/nix-${version}
    nixIncludes=${libraries}/build/include
    source ${libraries.setup}
    cp "$runtime/crt0.o" build/crt0.o
    for source in ${../../tests/libutil}/*.cpp; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -I ${libraries}/meson-build/subprojects/nix-store/libnixstore.a.p \
        -c "$source" -o "build/test-$(basename "$source" .cpp).o"
    done
    # Keep the libraries' static initializers and assertion wrapper; discard unused sections.
    ${llvmPackages.lld}/bin/ld.lld --gc-sections -static -nostdlib --wrap=__assert_fail \
      -T "$runtime/plan9.ld" -o "$out/probe.elf" --start-group \
      build/*.o ${compression}/lib/*.a ${sodium}/lib/libsodium.a ${sqlite}/lib/libsqlite3.a \
      ${dependencies.boost}/lib/*.a ${dependencies.digests}/lib/*.a \
      "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --whole-archive ${libraries}/build/libnix{util,store}.a --no-whole-archive --end-group
    cp ${libraries}/meson-build/cli/nix-{store,instantiate}.elf "$out/"
  ''
