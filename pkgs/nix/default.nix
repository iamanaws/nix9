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
    mkdir -p build/cli build/eval "$out"
    nixSource=${libraries}/nix-${version}
    nixIncludes=${libraries}/build/include
    source ${libraries.setup}
    cp "$runtime/crt0.o" build/crt0.o
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -c ${./store-platform.cc} -o build/store-platform.o
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -c ${./build-platform.cc} -o build/store-builder.o
    libraryObjects=(${libraries}/build/*.o build/*.o)
    for source in ${../../tests/libutil}/*.cpp; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$source" -o "build/test-$(basename "$source" .cpp).o"
    done
    # Discard unused functions and their unported dependencies.
    ${llvmPackages.lld}/bin/ld.lld --gc-sections -static -nostdlib \
      -T "$runtime/plan9.ld" -o "$out/probe.elf" --start-group \
      ${libraries}/build/*.o build/*.o ${compression}/lib/*.a ${sodium}/lib/libsodium.a ${sqlite}/lib/libsqlite3.a \
      ${dependencies.boost}/lib/*.a ${dependencies.digests}/lib/*.a \
      "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --end-group
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -c ${./main.cc} -o build/cli/main.o
    ${llvmPackages.lld}/bin/ld.lld --gc-sections -static -nostdlib \
      -T "$runtime/plan9.ld" -o "$out/nix-store.elf" --start-group \
      "''${libraryObjects[@]}" ${libraries}/build/cli/*.o build/cli/*.o \
      ${compression}/lib/*.a ${sodium}/lib/libsodium.a ${sqlite}/lib/libsqlite3.a \
      ${dependencies.boost}/lib/*.a ${dependencies.digests}/lib/*.a \
      "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --end-group

    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" -DNIX_INSTANTIATE \
      -c ${./main.cc} -o build/eval/main.o
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -c ${./eval-platform.cc} -o build/eval/platform.o
    ${llvmPackages.lld}/bin/ld.lld --gc-sections -static -nostdlib \
      -T "$runtime/plan9.ld" -o "$out/nix-instantiate.elf" --start-group \
      "''${libraryObjects[@]}" ${libraries}/build/cli/libmain_*.o ${libraries}/build/eval/*.o build/eval/*.o \
      ${compression}/lib/*.a ${sodium}/lib/libsodium.a ${sqlite}/lib/libsqlite3.a \
      ${dependencies.boost}/lib/*.a ${dependencies.digests}/lib/*.a \
      "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --end-group
  ''
