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
  patches = [ ./selected-system.patch ];
  buildPhase = ''
    mk 6.authsrv 6.keyfs 6.cron
    @{ cd factotum; mk 6.factotum }
  '';
  installPhase = ''
    mkdir -p $out/bin/auth
    cp 6.authsrv $out/bin/auth/authsrv
    cp 6.keyfs $out/bin/auth/keyfs
    cp 6.cron $out/bin/auth/cron
    cp factotum/6.factotum $out/bin/auth/factotum
  '';
}
