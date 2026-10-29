{
  mkDerivation,
  src,
  libauth,
  libauthsrv,
  libsec,
  libmp,
  libbio,
  exportfs,
}:
mkDerivation {
  name = "rcpu";
  inherit src;
  buildInputs = [
    libauth
    libauthsrv
    libsec
    libmp
    libbio
  ];
  buildCommand = ''
    mkdir -p $out/bin
    for(command in tlsclient tlssrv) {
      cp $src/sys/src/cmd/$command.c $command.c
      6c -o $command.6 $command.c
      6l -o $out/bin/$command $command.6
    }
    # Read the original scripts so cross-build shebang rewriting cannot leak in.
    sed 's,exportfs=/bin/exportfs,exportfs=${exportfs}/bin/exportfs,' $src/rc/bin/rcpu > $out/bin/rcpu
    cp $src/rc/bin/rconnect $out/bin/rconnect
    chmod 755 $out/bin/rcpu $out/bin/rconnect
  '';
}
