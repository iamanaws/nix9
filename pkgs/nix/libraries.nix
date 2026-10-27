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
  # Target libraries lack pkg-config files; compile_args exports their header paths.
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
      ['toml11', '${toml11.version}', '${toml11}/include', []],
      ['nlohmann_json', '${nlohmann_json.version}', '${nlohmann_json}/include', []],
    ]
      meson.override_dependency(dep[0], declare_dependency(
        version: dep[1],
        compile_args: ['-isystem' + dep[2]],
        link_args: dep[3],
      ))
    endforeach
    foreach name : ['common', 'dec', 'enc']
      meson.override_dependency('libbrotli' + name, declare_dependency(
        version: '${brotli.version}',
        compile_args: ['-isystem${compression}/include'],
        link_args: '${compression}/lib/libbrotli' + name + '.a',
      ))
    endforeach
    foreach part : ['util', 'store', 'fetchers', 'expr', 'main']
      subproject('nix-' + part)
    endforeach
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
    tar -xzf ${source}
    cd nix-${version}
    patch -p1 < ${./patches/brotli-truncation.patch}
    patch -p1 < ${./patches/store-cache.patch}
    patch -p1 < ${./patches/store-cycles.patch}
    patch -p1 < ${./patches/store-repair.patch}
    patch -p1 < ${./patches/version-without-store.patch}
    patch -p1 < ${./patches/gc-query.patch}
    patch -p1 < ${./patches/cc9-compat.patch}
    patch -p1 < ${./patches/9front.patch}
    patch -p1 < ${./patches/eval-fetch.patch}
    patch -p1 < ${./patches/meson.patch}
    cd ..
    nixSource="$PWD/nix-${version}"
    mkdir -p library-project/subprojects
    cp ${libraryProject} library-project/meson.build
    for part in util store fetchers expr main; do
      ln -s "$nixSource/src/lib$part" "library-project/subprojects/nix-$part"
    done
    mkdir "$nixSource/src/libstore/plan9"
    cp ${./store-platform.cc} "$nixSource/src/libstore/plan9/store-platform.cc"
    cp ${./build-platform.cc} "$nixSource/src/libstore/plan9/build-platform.cc"
    cp ${./filetransfer-platform.cc} "$nixSource/src/libstore/plan9/filetransfer-platform.cc"
    mkdir "$nixSource/src/libfetchers/plan9"
    cp ${./eval-platform.cc} "$nixSource/src/libfetchers/plan9/eval-platform.cc"
    substitute ${cc9.meson} cross.ini \
      --subst-var-by runtime ${cc9} \
      --subst-var-by clang ${llvmPackages.clang-unwrapped} \
      --subst-var-by llvm ${llvmPackages.llvm} \
      --subst-var-by lld ${llvmPackages.lld}
    meson setup meson-build library-project --cross-file "$PWD/cross.ini" \
      --wrap-mode=nofallback -Dbuildtype=plain -Doptimization=2 --prefix=/nix --sysconfdir=/etc \
      -Dnix-util:cpuid=disabled -Dnix-store:seccomp-sandboxing=disabled \
      -Dnix-store:s3-aws-auth=disabled -Dnix-store:sandbox-shell= -Dnix-expr:gc=disabled
    ninja -C meson-build -j "$NIX_BUILD_CORES"
    meson install -C meson-build --no-rebuild --destdir "$TMPDIR/install"
    cp -R "$TMPDIR/install/nix/"{include,lib} "$out/"
    for pc in "$out"/lib/pkgconfig/*.pc; do
      substituteInPlace "$pc" --replace-fail 'prefix=/nix' "prefix=$out"
    done
    cp meson-build/subprojects/nix-util/util-config-private.hh include/
    cp meson-build/subprojects/nix-util/unix/util-unix-config-private.hh include/
    cp meson-build/subprojects/nix-store/store-config-private.hh include/
    cp meson-build/subprojects/nix-expr/expr-config-private.hh include/
  ''
