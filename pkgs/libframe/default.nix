{
  mkDerivation,
  src,
  libdraw,
}:
mkDerivation {
  name = "libframe";
  inherit src;
  propagatedBuildInputs = [ libdraw ];
  makeFlags = [ "LIB=libframe.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libframe.a $out/lib/
  '';
}
