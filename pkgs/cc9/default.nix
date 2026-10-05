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
  libc = fetchurl {
    url = "https://raw.githubusercontent.com/Alino/agent9/3022c5609caa189aeb556d7d3828f471efd05f62/cc9/runtime/n9libc.c";
    hash = "sha256:80c2b2b5020c7af5e8e31a41feff25088a2f9d0284a59a3267128073bdd7ebf0";
  };
  fs = fetchurl {
    url = "https://raw.githubusercontent.com/Alino/agent9/3022c5609caa189aeb556d7d3828f471efd05f62/cc9/runtime/fs.c";
    hash = "sha256:e67a5cddba83cc42c2bb4b4ccff44e159ce33552ea8ca8b795584494d4cb457e";
  };
  posix = fetchurl {
    url = "https://raw.githubusercontent.com/Alino/agent9/3022c5609caa189aeb556d7d3828f471efd05f62/cc9/runtime/posix_llvm.c";
    hash = "sha256:8a471889cb7c6284b11f8b72ed805c0c36fc6074353d6a1b733b54165b3e2707";
  };
  poll = fetchurl {
    url = "https://raw.githubusercontent.com/Alino/agent9/3022c5609caa189aeb556d7d3828f471efd05f62/cc9/runtime/poll.c";
    hash = "sha256:59cb8d283d37a8367909c5b3bad4da69edca879274bff2baab2a1185e78001ef";
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
    cp ${libc} n9libc.c
    cp ${fs} fs.c
    cp ${posix} posix_llvm.c
    cp ${poll} poll.c
    chmod u+w crt0.c n9libc.c fs.c posix_llvm.c poll.c
    patch -p1 < ${./exit-status.patch}
    patch -p1 < ${./aligned-allocation.patch}
    patch -p1 < ${./environment.patch}
    patch -p1 < ${./exec-path.patch}
    patch -p1 < ${./create-mode.patch}
    patch -p1 < ${./poll-interruption.patch}
    runtime="$out"
    source ${./setup.sh}
    # Rebuild only the runtime units with local fixes.
    ${llvmPackages.clang-unwrapped}/bin/clang "''${cc9Flags[@]}" -std=c11 \
      -fexceptions -funwind-tables -femulated-tls -c crt0.c -o "$out/crt0.o"
    for unit in n9libc fs posix_llvm poll; do
      ${llvmPackages.clang-unwrapped}/bin/clang "''${cc9Flags[@]}" -O2 -fno-builtin \
        -fexceptions -funwind-tables -femulated-tls -c "$unit.c" -o "$unit.o"
    done
    chmod u+w "$out/libcc9cxx.a"
    ${llvmPackages.llvm}/bin/llvm-ar rcs "$out/libcc9cxx.a" n9libc.o fs.o posix_llvm.o poll.o
  ''
