{
  lib,
  runCommand,
  fetchurl,
  llvmPackages,
  boost,
  nlohmann_json,
  callPackage,
  bison,
  flex,
  toml11,
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
        ;
    };
    nativeBuildInputs = [
      bison
      flex
    ];
    meta = {
      description = "Experimental native Nix store and evaluator for 9front";
      license = lib.licenses.lgpl21Plus;
    };
  }
  ''
    mkdir build
    tar -xzf ${source}
    cd nix-${version}
    patch -p1 < ${./patches/brotli-truncation.patch}
    patch -p1 < ${./patches/store-cache.patch}
    patch -p1 < ${./patches/store-cycles.patch}
    patch -p1 < ${./patches/version-without-store.patch}
    patch -p1 < ${./patches/9front.patch}
    cd ..
    runtime=${cc9}
    source ${cc9.setup}
    cp "$runtime/crt0.o" build/crt0.o
    sources="$PWD/nix-${version}/src/libutil"
    mkdir -p build/include/nix/{util,store}
    cp ${./config/config.hh} build/include/nix/util/config.hh
    cp ${./config/store-config.hh} build/include/nix/store/config.hh
    cp ${./config/store-config-private.hh} build/include/store-config-private.hh
    cp ${./config/util-config-private.hh} build/include/util-config-private.hh
    cp ${./config/util-unix-config-private.hh} build/include/util-unix-config-private.hh
    echo '#define HAVE_PUBSETBUF 0' > build/include/main-config-private.hh
    # Use the same schema as upstream LocalStore.
    for schema in schema ca-specific-schema; do
      sed '1iR"sql(' "$sources/../libstore/$schema.sql" > "build/include/$schema.sql.gen.hh"
      echo ')sql"' >> "build/include/$schema.sql.gen.hh"
    done
    flags=(
      "''${cc9CxxFlags[@]}"
      -isystem ${boost.dev}/include -isystem ${nlohmann_json}/include
      -isystem ${sodium}/include -isystem ${sqlite}/include
      -isystem ${dependencies.digests}/include
      -isystem ${compression}/include
      -I "$sources/include" -I "$sources/unix/include"
      -I "$sources/../libstore/include" -I "$sources/../libmain/include"
      -I "$sources/../libcmd/include" -I "$sources/../nix"
      -I "$sources/widecharwidth" -I "$PWD/build/include"
    )
    # Compile real upstream translation units. No Linux libraries are linked.
    for source in \
      archive args base-n base-nix-32 canon-path compression compression-algo config-global configuration \
      current-process english environment-variables error executable-path exit experimental-features \
      file-content-address file-descriptor file-system fs-sink git hash hilite json-utils logging memory-source-accessor \
      mounted-source-accessor nar-accessor nar-listing pos-table position posix-source-accessor processes serialise \
      signature/local-keys source-accessor source-path strings suggestions tarfile terminal thread-pool union-source-accessor url users util xml-writer \
      unix/environment-variables unix/file-descriptor unix/file-path \
      unix/file-system-at unix/file-system unix/processes unix/signals unix/users unix/xdg-dirs; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$sources/$source.cc" -o "build/nix-''${source//\//_}.o"
    done
    for source in \
      build/derivation-builder build-result common-protocol content-address derivation-options derivations \
      derived-path derived-path-map downstream-placeholder export-import globals indirect-root-store keys \
      local-fs-store local-store log-store misc names nar-info nar-info-disk-cache outputs-spec parsed-derivations \
      path path-info path-references path-with-outputs pathlocks posix-fs-canonicalise profiles realisation references sqlite store-api store-dir-config \
      store-reference store-registration unix/pathlocks worker-protocol; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$sources/../libstore/$source.cc" -o "build/store-''${source//\//_}.o"
    done
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -c ${./store-platform.cc} -o build/store-platform.o
    libraryObjects=(build/*.o)
    for source in ${../../tests/libutil}/*.cpp; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$source" -o "build/test-$(basename "$source" .cpp).o"
    done
    mkdir -p "$out"
    # Discard unused functions and their unported dependencies.
    ${llvmPackages.lld}/bin/ld.lld --gc-sections -static -nostdlib \
      -T "$runtime/plan9.ld" -o "$out/probe.elf" --start-group \
      build/*.o ${compression}/lib/*.a ${sodium}/lib/libsodium.a ${sqlite}/lib/libsqlite3.a \
      ${dependencies.boost}/lib/*.a ${dependencies.digests}/lib/*.a \
      "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --end-group
    mkdir build/cli
    for source in libmain/{shared,common-args,loggers,plugin} nix/nix-store/{nix-store,dotgraph,graphml}; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$sources/../$source.cc" -o "build/cli/''${source//\//_}.o"
    done
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -c ${./main.cc} -o build/cli/main.o
    ${llvmPackages.lld}/bin/ld.lld --gc-sections -static -nostdlib \
      -T "$runtime/plan9.ld" -o "$out/nix-store.elf" --start-group \
      "''${libraryObjects[@]}" build/cli/*.o \
      ${compression}/lib/*.a ${sodium}/lib/libsodium.a ${sqlite}/lib/libsqlite3.a \
      ${dependencies.boost}/lib/*.a ${dependencies.digests}/lib/*.a \
      "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --end-group

    mkdir -p build/eval build/include/nix/expr build/include/primops
    echo '#define NIX_USE_BOEHMGC 0' > build/include/nix/expr/config.hh
    printf '#define HAVE_SYSCONF 0\n#define HAVE_TOML11_4 1\n' > build/include/expr-config-private.hh
    for name in primops/derivation.nix imported-drv-to-derivation.nix fetchurl.nix; do
      sed '1iR"nix(' "$sources/../libexpr/$name" > "build/include/$name.gen.hh"
      echo ')nix"' >> "build/include/$name.gen.hh"
    done
    bison -d -o build/include/parser-tab.cc "$sources/../libexpr/parser.y"
    flex -Cf --outfile=build/include/lexer-tab.cc --header-file=build/include/lexer-tab.hh \
      "$sources/../libexpr/lexer.l"
    flags+=(
      -I "$sources/../libexpr" -I "$sources/../libexpr/include"
      -I "$sources/../libfetchers/include" -isystem ${toml11}/include
    )
    for source in \
      attr-path attr-set diagnose eval-error eval-gc eval-profiler-settings eval-profiler eval-settings eval \
      function-trace get-drvs json-to-value lexer-helpers nixexpr paths primops print-ambiguous print \
      search-path value-to-json value-to-xml value value/context primops/context primops/fromTOML; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$sources/../libexpr/$source.cc" -o "build/eval/expr-''${source//\//_}.o"
    done
    for source in attrs cache fetch-settings fetch-to-store fetchers filtering-source-accessor input-cache; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$sources/../libfetchers/$source.cc" -o "build/eval/fetchers-$source.o"
    done
    for source in build/include/{parser-tab,lexer-tab}.cc ${./eval-main.cc} ${./eval-platform.cc}; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$source" -o "build/eval/$(basename "$source").o"
    done
    ${llvmPackages.lld}/bin/ld.lld --gc-sections -static -nostdlib \
      -T "$runtime/plan9.ld" -o "$out/nix-eval.elf" --start-group \
      "''${libraryObjects[@]}" build/cli/libmain_*.o build/eval/*.o \
      ${compression}/lib/*.a ${sodium}/lib/libsodium.a ${sqlite}/lib/libsqlite3.a \
      ${dependencies.boost}/lib/*.a ${dependencies.digests}/lib/*.a \
      "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --end-group
  ''
