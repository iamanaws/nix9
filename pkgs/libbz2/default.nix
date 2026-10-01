{
  runCommand,
  fetchurl,
  lib,
  gcc,
  cTools,
  sysroot,
}:
let
  source = fetchurl {
    url = "https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz";
    hash = "sha256-q1oDF27hBtPw+pDjgdpHjdrkBZGBU8yiSOaCzQxKImk=";
  };
in
runCommand "libbz2-1.0.8-9front"
  {
    nativeBuildInputs = [
      gcc
      cTools
    ];
    ccroot = sysroot;
    passthru = { inherit source; };
    meta = {
      description = "bzip2 static library for 9front using APE";
      homepage = "https://sourceware.org/bzip2/";
      license = lib.licenses.bsdOriginal;
    };
  }
  ''
    tar -xzf ${source}
    cd bzip2-1.0.8
    source ${../../lib/ape-build.sh}
    for unit in blocksort huffman crctable randtable compress decompress bzlib; do
      apeCompile "$unit.c" "$unit.6" c99 -D_POSIX_SOURCE
    done
    9ar rc libbz2.a *.6
    install -Dm644 libbz2.a "$out/lib/libbz2.a"
    install -Dm644 bzlib.h "$out/include/bzlib.h"
    install -Dm644 LICENSE "$out/share/doc/libbz2/LICENSE"
  ''
