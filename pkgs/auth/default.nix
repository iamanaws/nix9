{
  mkDerivation,
  src,
  libauth,
  libauthsrv,
  lib9p,
  libip,
  libregexp,
  libString,
}:
mkDerivation {
  name = "auth";
  inherit src;
  buildInputs = [
    libauth
    libauthsrv
    lib9p
    libip
    libregexp
    libString
  ];
  buildPhase = ''
    mk 6.authsrv 6.keyfs
    @{ cd factotum; mk 6.factotum }
  '';
  installPhase = ''
    mkdir -p $out/bin/auth
    cp 6.authsrv $out/bin/auth/authsrv
    cp 6.keyfs $out/bin/auth/keyfs
    cp factotum/6.factotum $out/bin/auth/factotum
  '';
}
