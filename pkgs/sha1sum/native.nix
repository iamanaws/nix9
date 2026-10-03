{
  mkDerivation,
  src,
  libsec,
}:
mkDerivation {
  name = "sha1sum";
  inherit src libsec;
  buildCommand = ''
    $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -o sha1sum.6 $src
    $tools/bin/mkdir -p $out/bin
    $tools/bin/6l -l -E _main -o $out/bin/sha1sum sha1sum.6 $libsec/lib/libsec.a $tools/amd64/lib/libc.a
  '';
}
