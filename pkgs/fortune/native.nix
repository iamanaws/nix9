{
  mkDerivation,
  src,
  libbio,
}:
mkDerivation {
  name = "fortune";
  inherit src libbio;
  buildCommand = ''
    $tools/bin/sed 's,/sys/games/lib,'^$out^'/share/fortune,g' $src/sys/src/cmd/fortune.c > fortune.c
    $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -o fortune.6 fortune.c
    $tools/bin/mkdir -p $out/bin $out/share/fortune
    $tools/bin/6l -s -l -E _main -o $out/bin/fortune fortune.6 $libbio/lib/libbio.a $tools/amd64/lib/libc.a
    $tools/bin/cp $src/sys/games/lib/fortunes $out/share/fortune/fortunes
    $out/bin/fortune > /dev/null
  '';
}
