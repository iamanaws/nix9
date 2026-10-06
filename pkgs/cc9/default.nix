{
  stdenvNoCC,
  fetchgit,
  llvmPackages_22,
  openlibm,
  cmake,
  ninja,
  python3,
}:
let
  source = fetchgit {
    url = "https://github.com/Alino/agent9.git";
    rev = "3022c5609caa189aeb556d7d3828f471efd05f62";
    sparseCheckout = [ "cc9" ];
    hash = "sha256-8eHDF02kRnw2KKS56eJgY++5jO0Y1w2DAqD63KOb/1Q=";
  };
in
stdenvNoCC.mkDerivation {
  pname = "cc9-runtime";
  version = "0.2.2";
  src = source;
  sourceRoot = "${source.name}/cc9";
  nativeBuildInputs = [
    cmake
    ninja
    python3
  ];
  dontConfigure = true;
  dontStrip = true;
  dontPatchELF = true;

  passthru = {
    elf2aout = "${source}/cc9/host/elf2aout.py";
    setup = ./setup.sh;
    cmake = ./toolchain.cmake;
    meson = ./meson.ini;
  };

  postPatch = ''
    for patchFile in ${./exit-status.patch} ${./aligned-allocation.patch} \
      ${./environment.patch} ${./exec-path.patch} ${./create-mode.patch} ${./poll-interruption.patch} ${./assert-noreturn.patch}; do
      patch --fuzz=0 -d runtime -p1 < "$patchFile"
    done
    substituteInPlace host/regen-libcxx.sh --replace-fail "sed -i ${"''"}" "sed -i"
    substituteInPlace host/build-runtime.sh --replace-fail 'O="/tmp/cc9-rt"' 'O="$TMPDIR/cc9-rt"'
    substituteInPlace host/build-libm.sh --replace-fail 'O=/tmp/cc9-libm' 'O=$TMPDIR/cc9-libm'
  '';

  buildPhase = ''
    runHook preBuild
    mkdir tools
    ln -s ${llvmPackages_22.clang-unwrapped}/bin/clang{,++} tools/
    ln -s ${llvmPackages_22.llvm}/bin/llvm-ar tools/
    export CC9_LLVM="$PWD/tools"
    cp -rs ${llvmPackages_22.libcxx.src} llvm-source
    chmod u+w llvm-source
    ln -s ${llvmPackages_22.libunwind.src}/libunwind llvm-source/libunwind
    export CC9_LLVMPROJ="$PWD/llvm-source" CC9_LLVMSRC="$PWD/llvm-source"
    export CC9_LIBCXX_TREE="$TMPDIR/libcxx-headers"
    bash host/regen-libcxx.sh
    export CC9_LIBCXX="$CC9_LIBCXX_TREE/include/c++/v1"
    bash host/build-runtime.sh
    export CC9_OPENLIBM=${openlibm.src}
    bash host/build-libm.sh
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/sysinc"
    cp lib/libcc9{cxx,m}.a "$TMPDIR/cc9-rt/crt0.o" test/plan9.ld "$out/"
    cp -RL runtime/include "$out/sysinc/cc9"
    cp -RL "$CC9_LIBCXX" "$out/sysinc/cxxv1"
    runHook postInstall
  '';
}
