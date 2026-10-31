{
  mkDerivation,
  src,
  libframe,
  libplumb,
  libbio,
  lib9p,
  libcomplete,
  libsec,
  fonts,
}:
mkDerivation {
  name = "acme";
  inherit src;
  buildInputs = [
    libframe
    libplumb
    libbio
    lib9p
    libcomplete
    libsec
  ];
  sourceRoot = "source/sys/src/cmd/acme";
  postUnpack = ''
    sed -e 's,/acme/bin,'^$out^'/bin,g' \
      -e 's,/lib/font/bit/vga/unicode.font,${fonts}/share/fonts/dejavu/dejavu.12.font,g' \
      acme.c > acme.tmp
    mv acme.tmp acme.c
  '';
  buildPhase = ''
    mk
    @{ cd $TMPDIR/source/acme/bin/source/win; mk }
  '';
  installPhase = ''
    mkdir -p $out/bin/amd64
    cp 6.out $out/bin/acme
    cp $TMPDIR/source/acme/bin/source/win/6.out $out/bin/amd64/winfs
    sed 's,/acme/bin,'^$out^'/bin,g' $src/acme/bin/win > $out/bin/win
    chmod 755 $out/bin/win
  '';
}
