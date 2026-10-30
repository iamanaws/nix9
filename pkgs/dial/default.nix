{ mkDerivation, src }:
mkDerivation {
  name = "dial";
  inherit src;
  buildCommand = ''
    cp $src dial.c
    6c -o dial.6 dial.c
    mkdir -p $out/bin
    6l -o $out/bin/dial dial.6
  '';
}
