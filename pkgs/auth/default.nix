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
  patches = [
    ./selected-system.patch
    ./keyfs-service.patch
  ];
  buildPhase = ''
    mk 6.authsrv 6.keyfs 6.cron 6.changeuser
    @{ cd factotum; mk 6.factotum }
    6c -o checkuser.6 ${./checkuser.c}
    6l -o checkuser checkuser.6
  '';
  installPhase = ''
    mkdir -p $out/bin/auth
    cp 6.authsrv $out/bin/auth/authsrv
    cp 6.keyfs $out/bin/auth/keyfs
    cp 6.cron $out/bin/auth/cron
    cp 6.changeuser $out/bin/auth/changeuser
    cp factotum/6.factotum $out/bin/auth/factotum
    cp checkuser $out/bin/auth/checkuser
  '';
}
