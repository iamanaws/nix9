{
  mkDerivation,
  src,
  libbio,
  libip,
}:
mkDerivation {
  name = "libndb";
  inherit src;
  propagatedBuildInputs = [
    libbio
    libip
  ];
  makeFlags = [ "LIB=libndb.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libndb.a $out/lib/
  '';
}
