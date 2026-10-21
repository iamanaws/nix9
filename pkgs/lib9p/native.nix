{
  mkDerivation,
  src,
  libauth,
  libthread,
}:
mkDerivation {
  name = "lib9p";
  inherit src;
  propagatedBuildInputs = [
    libauth
    libthread
  ];
  makeFlags = [ "LIB=lib9p.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp lib9p.a $out/lib/
  '';
}
