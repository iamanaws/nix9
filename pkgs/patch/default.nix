{
  mkDerivation,
  src,
  libbio ? null,
}:
mkDerivation {
  name = "patch";
  inherit src;
  buildInputs = if libbio == null then [ ] else [ libbio ];
  buildCommand = ''
    cp $src patch.c
    6c -o patch.6 patch.c
    mkdir -p $out/bin
    6l -o $out/bin/patch patch.6
  '';
}
