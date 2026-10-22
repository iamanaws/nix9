{
  mkDerivation,
  src,
  libsec,
}:
mkDerivation {
  name = "sha1sum";
  inherit src;
  passthru.source = src;
  buildInputs = [ libsec ];
  buildCommand = ''
    6c -o sha1sum.6 $src
    mkdir -p $out/bin
    6l -o $out/bin/sha1sum sha1sum.6
  '';
}
