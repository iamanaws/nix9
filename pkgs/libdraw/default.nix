{
  mkDerivation,
  src,
  libthread,
}:
mkDerivation {
  name = "libdraw";
  inherit src;
  propagatedBuildInputs = [ libthread ];
  makeFlags = [ "LIB=libdraw.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libdraw.a $out/lib/
  '';
}
