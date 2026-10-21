{
  mkDerivation,
  src,
  patch,
}:
mkDerivation {
  name = "ar";
  inherit src;
  nativeBuildInputs = [ patch ];
  patches = [ ./source-date-epoch.patch ];
  sourceRoot = ".";
  unpackPhase = ''
    cp $src ar.c
    chmod u+w ar.c
  '';
  buildPhase = ''
    6c -FTVw -o ar.6 ar.c
    6l -o ar ar.6
  '';
  installPhase = ''
    mkdir -p $out/bin
    cp ar $out/bin/ar
  '';
  meta.description = "Plan 9 archive tool";
}
