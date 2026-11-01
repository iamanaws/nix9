{
  mkDerivation,
  src,
  libbio,
  libip,
}:
mkDerivation {
  name = "libndb";
  inherit src;
  # Include IPv4 /0 through /3 in native subnet inheritance.
  patches = [ ./ipv4-default-network.patch ];
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
