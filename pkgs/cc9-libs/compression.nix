{
  runCommand,
  cmake,
  ninja,
  llvmPackages,
  libarchive,
  brotli,
  zlib,
  xz,
  zstd,
  cc9,
}:
runCommand "cc9-compression"
  {
    nativeBuildInputs = [
      cmake
      ninja
    ];
  }
  ''
    tar -xzf ${zlib.src}
    tar -xJf ${xz.src}
    cp -R ${libarchive.src} libarchive
    chmod -R u+w libarchive
    patch -d libarchive -p1 < ${./libarchive.patch}
    substitute ${cc9.cmake} toolchain.cmake \
      --subst-var-by runtime ${cc9} \
      --subst-var-by prefix "$out" \
      --subst-var-by clang ${llvmPackages.clang-unwrapped} \
      --subst-var-by llvm ${llvmPackages.llvm} \
      --subst-var-by lld ${llvmPackages.lld}
    toolchain="$PWD/toolchain.cmake"
    build() {
      name="$1"; source="$2"; shift 2
      cmake -S "$source" -B "$name-build" -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE="$toolchain" \
        -DCMAKE_INSTALL_PREFIX="$out" -DCMAKE_INSTALL_LIBDIR=lib \
        -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF "$@"
      cmake --build "$name-build" -j "$NIX_BUILD_CORES"
      cmake --install "$name-build"
    }
    build zlib zlib-${zlib.version} -DZLIB_BUILD_SHARED=OFF -DZLIB_BUILD_TESTING=OFF
    build brotli ${brotli.src} -DBROTLI_BUILD_TOOLS=OFF -DBROTLI_DISABLE_TESTS=ON
    build xz xz-${xz.version} -DXZ_THREADS=no -DXZ_NLS=OFF \
      -DXZ_TOOL_XZ=OFF -DXZ_TOOL_XZDEC=OFF -DXZ_TOOL_LZMADEC=OFF \
      -DXZ_TOOL_LZMAINFO=OFF -DXZ_TOOL_SCRIPTS=OFF
    build zstd ${zstd.src}/build/cmake -DZSTD_BUILD_PROGRAMS=OFF \
      -DZSTD_BUILD_TESTS=OFF -DZSTD_BUILD_SHARED=OFF -DZSTD_MULTITHREAD_SUPPORT=OFF
    # cc9 has posix_spawnp but lacks the spawn attribute functions.
    build archive libarchive -DPOSIX_REGEX_LIB=NONE -DHAVE_POSIX_SPAWNP=OFF \
      -DENABLE_OPENSSL=OFF -DENABLE_LIBB2=OFF -DENABLE_LZ4=OFF -DENABLE_BZip2=OFF \
      -DENABLE_LIBXML2=OFF -DENABLE_EXPAT=OFF -DENABLE_PCREPOSIX=OFF -DENABLE_PCRE2POSIX=OFF \
      -DENABLE_LIBGCC=OFF -DENABLE_TAR=OFF -DENABLE_CPIO=OFF -DENABLE_CAT=OFF -DENABLE_UNZIP=OFF \
      -DENABLE_XATTR=OFF -DENABLE_ACL=OFF -DENABLE_ICONV=OFF -DENABLE_TEST=OFF
  ''
