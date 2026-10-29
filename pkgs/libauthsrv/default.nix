{
  mkDerivation,
  src,
  libbio,
  libsec,
  libmp,
  libndb,
  buildPackages,
}:
mkDerivation {
  name = "libauthsrv";
  inherit src;
  propagatedBuildInputs = [
    libbio
    libsec
    libmp
    libndb
  ];
  nativeBuildInputs = [ buildPackages.mpc ];
  makeFlags = [ "LIB=libauthsrv.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libauthsrv.a $out/lib/
  '';
}
