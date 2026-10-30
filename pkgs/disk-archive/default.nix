{
  mkDerivation,
  src,
  libbio,
  libdisk,
  libauth,
  libregexp,
  libsec,
}:
mkDerivation {
  name = "disk-archive";
  inherit src;
  patches = [ ./errors.patch ];
  buildInputs = [
    libbio
    libdisk
    libauth
    libregexp
    libsec
  ];
  buildPhase = ''
    6c -o proto.6 sys/src/libdisk/proto.c
    6c -o mkfs.6 sys/src/cmd/disk/mkfs.c
    6l -o mkfs mkfs.6 proto.6
    6c -o mkext.6 sys/src/cmd/disk/mkext.c
    6l -o mkext mkext.6
    6c -o checksum.6 ${./checksum.c}
    6l -o checksum checksum.6
  '';
  installPhase = ''
    mkdir -p $out/bin/disk
    cp mkfs mkext checksum $out/bin/disk/
    echo '#!/bin/rc' > $out/bin/disk/restore
    echo 'archiveTools='$out >> $out/bin/disk/restore
    cat ${./restore.rc} >> $out/bin/disk/restore
    chmod 755 $out/bin/disk/restore
  '';
}
