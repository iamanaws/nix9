{
  mkDerivation,
  src,
  lib9p,
  libip,
}:
mkDerivation {
  name = "tftpfs";
  inherit src;
  buildInputs = [
    lib9p
    libip
  ];
  buildCommand = ''
    cp $src tftpfs.c
    chmod u+w tftpfs.c
    # UDP's 52-byte wire header excludes C struct padding on amd64.
    patch -p1 < ${./wire-header.patch}
    6c -o tftpfs.6 tftpfs.c
    mkdir -p $out/bin/ip
    6l -o $out/bin/ip/tftpfs tftpfs.6
  '';
}
