{
  mkDerivation,
  src,
  libplumb,
  libbio,
  libregexp,
  libauth,
}:
mkDerivation {
  name = "plumber";
  inherit src;
  sourceRoot = "source/sys/src/cmd/plumb";
  buildInputs = [
    libplumb
    libbio
    libregexp
    libauth
  ];
  buildFlags = [ "all" ];
  installPhase = ''
    mkdir -p $out/bin $out/share/plumb
    cp 6.plumb $out/bin/plumb
    cp 6.plumber $out/bin/plumber
    cp $src/sys/lib/plumb/fileaddr $out/share/plumb/
  '';
}
