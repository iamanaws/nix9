{ mkDerivation, src }:
mkDerivation {
  name = "ar";
  inherit src;
  buildCommand = ''
    mkdir -p $out/bin
    cp $src ar.c
    6c -FTVw -o ar.6 ar.c
    6l -o $out/bin/ar ar.6
  '';
  meta.description = "Plan 9 archive tool";
}
