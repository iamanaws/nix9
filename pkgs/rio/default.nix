{
  mkDerivation,
  src,
  libframe,
  libplumb,
  libcomplete,
}:
mkDerivation {
  name = "rio";
  inherit src;
  buildInputs = [
    libframe
    libplumb
    libcomplete
  ];
  sourceRoot = "source/sys/src/cmd/rio";
  installPhase = ''
    mkdir -p $out/bin
    cp 6.out $out/bin/rio
    for(command in window label wloc) {
      cp $src/rc/bin/$command $out/bin/$command
      chmod 755 $out/bin/$command
    }
  '';
}
