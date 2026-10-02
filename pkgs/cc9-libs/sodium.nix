{
  runCommand,
  llvmPackages,
  libsodium,
  cc9,
}:
runCommand "cc9-libsodium" { } ''
  mkdir build
  runtime=${cc9}
  source ${cc9.setup}
  cp -R ${libsodium.src} sodium
  chmod -R u+w sodium
  patch -d sodium -p1 < ${./sodium.patch}
  # Like upstream build.zig, build the C sources with an explicit feature set
  # and the supplied version header. No SIMD, mmap, mlock or guard pages.
  cp sodium/builds/msvc/version.h sodium/src/libsodium/include/sodium/version.h
  flags=(
    "''${cc9Flags[@]}" -std=c11 -O2 -DCONFIGURED=1 -femulated-tls
    -fno-strict-aliasing -fno-strict-overflow -fwrapv
    -DHAVE_STDINT_H=1 -DHAVE_INTTYPES_H=1 -DHAVE_TI_MODE=1
    -DHAVE_C_VARARRAYS=1 -DNATIVE_LITTLE_ENDIAN=1
    -DHAVE_PTHREAD=1 -DHAVE_ATOMIC_OPS=1 -DHAVE_C11_MEMORY_FENCES=1
    -DHAVE_GCC_MEMORY_FENCES=1 -DHAVE_GETPID=1 -DHAVE_CLOCK_GETTIME=1
    -DTLS=_Thread_local
    -I sodium/src/libsodium/include -I sodium/src/libsodium/include/sodium
  )
  for source in $(find sodium/src/libsodium -name '*.c' | sort); do
    ${llvmPackages.clang-unwrapped}/bin/clang "''${flags[@]}" \
      -c "$source" -o "build/''${source//\//_}.o"
  done
  mkdir -p "$out/lib" "$out/include"
  ${llvmPackages.llvm}/bin/llvm-ar rcs "$out/lib/libsodium.a" build/*.o
  cp -R sodium/src/libsodium/include/sodium{,.h} "$out/include/"
''
