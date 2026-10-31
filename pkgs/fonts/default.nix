{ mkDerivation, src }:
mkDerivation {
  name = "dejavu-fonts";
  inherit src;
  buildCommand = ''
    mkdir -p $out/share/fonts/dejavu
    cp $src/* $out/share/fonts/dejavu/
  '';
}
