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
    for part in BOOT/lib9 lib_core/libbio compilers/cck assemblers/6a linkers/6l compilers/6c; do
      (cd "$part"; mk install)
    done
    runHook postBuild
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin"
    cp ROOT/arch/boot-gcc/bin/6{a,c,l} "$out/bin/"
    runHook postInstall
  '';
  meta = {
    description = "Experimental Linux-hosted Plan 9 amd64 compiler, assembler, and linker";
    homepage = "https://github.com/aryx/goken9cc";
    platforms = [ "x86_64-linux" ];
  };
}
