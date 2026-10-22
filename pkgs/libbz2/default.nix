{
  mkDerivation,
  fetchurl,
  upstream ? import ./source.nix,
  libap,
  libbsd,
}:
let
  source = fetchurl upstream;
in
mkDerivation {
  pname = "libbz2";
  version = "1.0.8";
  src = source;
  passthru = { inherit source; };
  sourceRoot = "bzip2-1.0.8";
  propagatedBuildInputs = [
    libap
    libbsd
  ];
  buildPhase = ''
    for(unit in blocksort huffman crctable randtable compress decompress bzlib) {
      pcc -c -D_POSIX_SOURCE $unit^.c
    }
  '';
  installPhase = ''
    mkdir -p $out/lib/ape $out/include/ape $out/share/doc/libbz2
    ar rc $out/lib/ape/libbz2.a *.6
    cp bzlib.h $out/include/ape/
    cp LICENSE $out/share/doc/libbz2/
  '';
}
