{
  runCommand,
  meson,
  ninja,
  libarchive,
  libblake3,
  openssl,
  libsodium,
  brotli,
  writeText,
  llvmPackages,
  boost,
  nlohmann_json,
  bison,
  flex,
  toml11,
  source,
  version,
  cc9,
  dependencies,
}:
let
  inherit (dependencies) compression sodium sqlite;
  # These target libraries are built separately and do not all ship pkg-config files.
  libraryProject = writeText "meson.build" ''
    project('nix9-libraries', 'cpp')
    assert(meson.get_compiler('cpp').links('int main() { return 0; }'), 'Cannot link against the target runtime')
    foreach dep : [
      ['boost', '${boost.version}', '${boost.dev}/include', ['${dependencies.boost}/lib/libboost-target.a']],
      ['libblake3', '${libblake3.version}', '${dependencies.digests}/include', ['${dependencies.digests}/lib/libdigests.a']],
      ['libcrypto', '${openssl.version}', '${dependencies.digests}/include', ['${dependencies.digests}/lib/libdigests.a']],
      ['libarchive', '${libarchive.version}', '${compression}/include', ['${compression}/lib/libarchive.a', '${compression}/lib/libz.a', '${compression}/lib/liblzma.a', '${compression}/lib/libzstd.a']],
      ['libsodium', '${libsodium.version}', '${sodium}/include', ['${sodium}/lib/libsodium.a']],
      ['sqlite3', '${sqlite.version}', '${sqlite}/include', ['${sqlite}/lib/libsqlite3.a']],
      ['nlohmann_json', '${nlohmann_json.version}', '${nlohmann_json}/include', []],
    ]
      meson.override_dependency(dep[0], declare_dependency(
        version: dep[1],
        include_directories: include_directories(dep[2], is_system: true),
        link_args: dep[3],
      ))
    endforeach
    foreach name : ['common', 'dec', 'enc']
      meson.override_dependency('libbrotli' + name, declare_dependency(
        version: '${brotli.version}',
        include_directories: include_directories('${compression}/include', is_system: true),
        link_args: '${compression}/lib/libbrotli' + name + '.a',
      ))
    endforeach
    subproject('nix-util')
    subproject('nix-store')
  '';
  setup = writeText "nix9-compile-setup" ''
    runtime=${cc9}
    source ${cc9.setup}
    sources="$nixSource/src/libutil"
    flags=(
      "''${cc9CxxFlags[@]}"
      "-ffile-prefix-map=$nixSource=/build/nix-${version}"
      "-ffile-prefix-map=$nixIncludes=/build/include"
      -isystem ${boost.dev}/include -isystem ${nlohmann_json}/include
      -isystem ${sodium}/include -isystem ${sqlite}/include
      -isystem ${dependencies.digests}/include
      -isystem ${compression}/include
      -I "$sources/include" -I "$sources/unix/include"
      -I "$sources/../libstore/unix/include" -I "$sources/../libstore"
      -I "$sources/../libstore/include" -I "$sources/../libmain/include"
      -I "$sources/../libcmd/include" -I "$sources/../nix"
      -I "$sources/widecharwidth" -I "$nixIncludes"
      -I "$sources/../libexpr" -I "$sources/../libexpr/include"
      -I "$sources/../libfetchers/include" -isystem ${toml11}/include
    )
  '';
in
runCommand "nix-${version}-9front-libraries"
  {
    nativeBuildInputs = [
      meson
      ninja
      bison
      flex
    ];
    passthru = { inherit setup; };
  }
  ''
    mkdir -p "$out"
    cd "$out"
    mkdir build
    tar -xzf ${source}
    cd nix-${version}
    patch -p1 < ${./patches/brotli-truncation.patch}
    patch -p1 < ${./patches/store-cache.patch}
    patch -p1 < ${./patches/store-cycles.patch}
    patch -p1 < ${./patches/version-without-store.patch}
    patch -p1 < ${./patches/gc-query.patch}
    patch -p1 < ${./patches/cc9-compat.patch}
    patch -p1 < ${./patches/9front.patch}
    patch -p1 < ${./patches/meson.patch}
    cd ..
    sources="$PWD/nix-${version}/src/libutil"
    mkdir -p build/include/nix/{util,store}
    echo '#define HAVE_PUBSETBUF 0' > build/include/main-config-private.hh
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
    nixSource="$PWD/nix-${version}"
    nixIncludes="$PWD/build/include"
    source ${setup}
    mkdir -p library-project/subprojects
    cp ${libraryProject} library-project/meson.build
    ln -s "$nixSource/src/libutil" library-project/subprojects/nix-util
    ln -s "$nixSource/src/libstore" library-project/subprojects/nix-store
    mkdir "$nixSource/src/libstore/plan9"
    cp ${./store-platform.cc} "$nixSource/src/libstore/plan9/store-platform.cc"
    cp ${./build-platform.cc} "$nixSource/src/libstore/plan9/build-platform.cc"
    substitute ${cc9.meson} cross.ini \
      --subst-var-by runtime ${cc9} \
      --subst-var-by clang ${llvmPackages.clang-unwrapped} \
      --subst-var-by llvm ${llvmPackages.llvm} \
      --subst-var-by lld ${llvmPackages.lld}
    meson setup meson-build library-project --cross-file "$PWD/cross.ini" \
      --wrap-mode=nofallback -Dbuildtype=plain --prefix=/nix --sysconfdir=/etc \
      -Dnix-util:cpuid=disabled -Dnix-store:seccomp-sandboxing=disabled \
      -Dnix-store:s3-aws-auth=disabled -Dnix-store:sandbox-shell=
    ninja -C meson-build -j "$NIX_BUILD_CORES"
    cp meson-build/subprojects/nix-util/include/nix/util/config.hh build/include/nix/util/
    cp meson-build/subprojects/nix-util/util-config-private.hh build/include/
    cp meson-build/subprojects/nix-util/unix/util-unix-config-private.hh build/include/
    cp meson-build/subprojects/nix-store/include/nix/store/config.hh build/include/nix/store/
    cp meson-build/subprojects/nix-store/store-config-private.hh build/include/
    cp meson-build/subprojects/nix-{util,store}/libnix*.a build/
    # The remaining libraries still use the explicit source lists.
    mkdir build/cli
    for source in libmain/{shared,common-args,loggers,plugin} nix/nix-store/{nix-store,dotgraph,graphml}; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$sources/../$source.cc" -o "build/cli/''${source//\//_}.o"
    done
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
    for source in libcmd/common-eval-args nix/nix-instantiate/nix-instantiate; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$sources/../$source.cc" -o "build/eval/''${source//\//_}.o"
    done
    for source in build/include/{parser-tab,lexer-tab}.cc; do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$source" -o "build/eval/$(basename "$source").o"
    done
  ''
