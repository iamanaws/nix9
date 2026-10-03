{
  runCommand,
  fetchurl,
  llvmPackages,
}:
let
  archive = fetchurl {
    url = "https://github.com/Alino/agent9/releases/download/cc9-v0.2.2/cc9-amd64.tar.gz";
    hash = "sha256:dd6b7b7be9c544740e57fdbd207dcbf50eadc751ab805452d05b47884c22d184";
  };
  crt0 = fetchurl {
    url = "https://raw.githubusercontent.com/Alino/agent9/3022c5609caa189aeb556d7d3828f471efd05f62/cc9/runtime/crt0.c";
    hash = "sha256:dc7c521794bfa2b7a07720e40b5a18a1e1a527d27e31414e995904bce9c733fc";
  };
  elf2aout = fetchurl {
    url = "https://raw.githubusercontent.com/Alino/agent9/3022c5609caa189aeb556d7d3828f471efd05f62/cc9/host/elf2aout.py";
    hash = "sha256:0f1f502769c8c2d273649ddfed5b713c86ebe1f38017b66368f14004437fa8a5";
  };
in
runCommand "cc9-runtime-0.2.2"
  {
    passthru = {
      inherit archive elf2aout;
      setup = ./setup.sh;
      cmake = ./toolchain.cmake;
    };
  }
  ''
    tar -xzf ${archive} amd64/lib/cc9
    cp -R amd64/lib/cc9 "$out"
    cp ${crt0} crt0.c
    chmod u+w crt0.c
    patch -p1 < ${./exit-status.patch}
    runtime="$out"
    source ${./setup.sh}
    # Preserve numeric exit codes when main returns. Other runtime code is prebuilt.
    ${llvmPackages.clang-unwrapped}/bin/clang "''${cc9Flags[@]}" -std=c11 \
      -fexceptions -funwind-tables -femulated-tls -c crt0.c -o "$out/crt0.o"
  ''
