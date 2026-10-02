{
  lib,
  runCommand,
  llvmPackages,
  boost,
  cc9,
}:
runCommand "cc9-boost" { } ''
  mkdir build
  runtime=${cc9}
  source ${cc9.setup}
  flags=("''${cc9CxxFlags[@]}" -isystem ${boost.dev}/include)
  tar -xjf ${boost.src} boost_${
    lib.replaceStrings [ "." ] [ "_" ] boost.version
  }/libs/{context,url}/src
  patch -d boost_${lib.replaceStrings [ "." ] [ "_" ] boost.version} -p1 < ${./boost-url.patch}
    context="$PWD/boost_${lib.replaceStrings [ "." ] [ "_" ] boost.version}/libs/context/src"
    for source in make jump ontop; do
      ${llvmPackages.clang-unwrapped}/bin/clang --target=x86_64-unknown-none \
        -c "$context/asm/''${source}_x86_64_sysv_elf_gas.S" \
        -o "build/context-$source.o"
    done
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -c "$context/posix/stack_traits.cpp" -o build/context-stack-traits.o
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -c "$context/fcontext.cpp" -o build/context-fcontext.o
    url="$PWD/boost_${lib.replaceStrings [ "." ] [ "_" ] boost.version}/libs/url/src"
    for source in $(cd "$url" && find . -name '*.cpp' | sort); do
      ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
        -c "$url/$source" -o "build/url-''${source//\//_}.o"
    done
  mkdir -p "$out/lib"
  ${llvmPackages.llvm}/bin/llvm-ar rcs "$out/lib/libboost-target.a" build/*.o
''
