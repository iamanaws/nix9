{
  mkDerivation,
  src,
  libbio,
}:
mkDerivation {
  name = "fortune";
  inherit src;
  buildInputs = [ libbio ];
  sourceRoot = "source/sys/src/cmd";
  postUnpack = ''
    sed 's,/sys/games/lib,'^$out^'/share/fortune,g' fortune.c > fortune.tmp
    mv fortune.tmp fortune.c
  '';
  buildPhase = ''
    6c fortune.c
    6l -s -o fortune fortune.6
  '';
  installPhase = ''
    mkdir -p $out/bin $out/share/fortune
    cp fortune $out/bin/fortune
    cp ../../games/lib/fortunes $out/share/fortune/fortunes
    $out/bin/fortune > /dev/null
  '';
}
