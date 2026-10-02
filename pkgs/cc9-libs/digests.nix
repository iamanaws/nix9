{
  runCommand,
  llvmPackages,
  openssl,
  libblake3,
  perl,
  cc9,
}:
runCommand "cc9-digests" { nativeBuildInputs = [ perl ]; } ''
  mkdir build
  runtime=${cc9}
  source ${cc9.setup}
  tar -xzf ${openssl.src}
  cd openssl-${openssl.version}
  perl Configure gcc no-asm no-shared no-threads no-dso no-engine no-module no-tests
  make build_generated
  cd ..
  crypto="$PWD/openssl-${openssl.version}"
    cflags=(
      "''${cc9Flags[@]}" -std=c11
      -I "$crypto/include" -I "$crypto"
    )
    for source in md5/md5_dgst sha/sha1dgst sha/sha256 sha/sha512 mem_clr; do
      ${llvmPackages.clang-unwrapped}/bin/clang "''${cflags[@]}" \
        -c "$crypto/crypto/$source.c" -o "build/crypto-''${source//\//_}.o"
    done
    for source in blake3 blake3_dispatch blake3_portable; do
      ${llvmPackages.clang-unwrapped}/bin/clang "''${cflags[@]}" \
        -DBLAKE3_NO_SSE2 -DBLAKE3_NO_SSE41 -DBLAKE3_NO_AVX2 \
        -DBLAKE3_NO_AVX512 -DBLAKE3_USE_NEON=0 \
        -c ${libblake3.src}/c/$source.c -o "build/$source.o"
    done
  mkdir -p "$out/lib" "$out/include"
  ${llvmPackages.llvm}/bin/llvm-ar rcs "$out/lib/libdigests.a" build/*.o
  cp -R "$crypto/include/." "$out/include/"
  cp ${libblake3.src}/c/blake3.h "$out/include/"
''
