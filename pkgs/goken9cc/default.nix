{
  lib,
  stdenv,
  source,
}:
stdenv.mkDerivation {
  pname = "goken9cc-amd64";
  version = "unstable-2026-10-01";
  src = source;
  # This package targets 9front archives, whose member names occupy 16 bytes.
  # Upstream defaults to the historical Go fork's incompatible 64-byte field.
  patches = [
    ./plan9-archive.patch
    ./9front-amd64.patch
  ];
  configurePhase = ''
    runHook preConfigure
    patchShebangs configure scripts
    ./configure
    runHook postConfigure
  '';
  buildPhase = ''
    runHook preBuild
    ./scripts/build-mk.sh
    ./scripts/promote-mk.sh
    . ./env.sh
    export objtype cputype ostype
    for part in BOOT/lib9 lib_core/libbio lib_toolchain/libmach compilers/cck assemblers/6a linkers/6l compilers/6c linkers/ar; do
      (cd "$part"; mk install)
    done
    runHook postBuild
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    arTool="$PWD/ROOT/arch/boot-gcc/bin/iar"
    mkdir archive-check
    (
      cd archive-check
      for member in short.6 abcdefghijklm.6 abcdefghijklmn.6; do
        printf '%s\n' "$member" > "$member"
      done
      "$arTool" rc check.a short.6 abcdefghijklm.6 abcdefghijklmn.6
      "$arTool" t check.a > actual
      printf '%s\n' short.6 abcdefghijklm.6 abcdefghijklmn.6 > expected
      cmp expected actual
      mkdir extracted
      cd extracted
      "$arTool" x ../check.a
      for member in short.6 abcdefghijklm.6 abcdefghijklmn.6; do
        cmp "../$member" "$member"
      done
    )
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin"
    cp ROOT/arch/boot-gcc/bin/6{a,c,l} "$out/bin/"
    cp ROOT/arch/boot-gcc/bin/iar "$out/bin/9ar"
    runHook postInstall
  '';
  meta = {
    description = "Experimental Linux-hosted Plan 9 amd64 compiler, assembler, linker, and archiver";
    homepage = "https://github.com/aryx/goken9cc";
    platforms = [ "x86_64-linux" ];
  };
}
