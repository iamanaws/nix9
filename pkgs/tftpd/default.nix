{
  mkDerivation,
  src,
  libauth,
  libauthsrv,
  libbio,
  libip,
  libregexp,
  libsec,
  libmp,
}:
mkDerivation {
  name = "tftpd";
  inherit src;
  buildInputs = [
    libauth
    libauthsrv
    libbio
    libip
    libregexp
    libsec
    libmp
  ];
  buildCommand = ''
    cp $src tftpd.c
    6c -o tftpd.6 tftpd.c
    mkdir -p $out/bin/ip
    6l -o $out/bin/ip/tftpd tftpd.6
  '';
}
