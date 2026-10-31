{
  mkDerivation,
  src,
  libthread,
}:
mkDerivation {
  name = "libplumb";
  inherit src;
  propagatedBuildInputs = [ libthread ];
  makeFlags = [ "LIB=libplumb.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libplumb.a $out/lib/
  '';
}
