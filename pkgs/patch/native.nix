{ mkDerivation, src }:
mkDerivation {
  name = "patch";
  inherit src;
  buildCommand = ''
    cp $src patch.c
    6c -o patch.6 patch.c
    mkdir -p $out/bin
    6l -o $out/bin/patch patch.6
  '';
}
