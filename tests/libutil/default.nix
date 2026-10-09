{
  runCommand,
  llvmPackages,
  nixUtil,
}:
let
  inherit (nixUtil) version libraries dependencies;
  inherit (dependencies) compression sodium sqlite;
in
runCommand "nix-${version}-probe" { } ''
  mkdir -p build "$out"
  nixSource=${libraries}/nix-${version}
  nixIncludes=${libraries}/build/include
  source ${libraries.setup}
  cp "$runtime/crt0.o" build/crt0.o
  for source in ${./.}/*.cpp; do
    ${llvmPackages.clang-unwrapped}/bin/clang++ "''${flags[@]}" \
      -I ${libraries}/meson-build/subprojects/nix-store/libnixstore.a.p \
      -c "$source" -o "build/test-$(basename "$source" .cpp).o"
  done
  # Keep the libraries' static initializers and assertion wrapper; discard unused sections.
  ${llvmPackages.lld}/bin/ld.lld --gc-sections -static -nostdlib --wrap=__assert_fail --wrap=n9_pwrite \
    -T "$runtime/plan9.ld" -o "$out/probe.elf" --start-group \
    build/*.o ${compression}/lib/*.a ${sodium}/lib/libsodium.a ${sqlite}/lib/libsqlite3.a \
    ${dependencies.boost}/lib/*.a ${dependencies.digests}/lib/*.a \
    "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --whole-archive ${libraries}/build/libnix{util,store}.a --no-whole-archive --end-group
''
