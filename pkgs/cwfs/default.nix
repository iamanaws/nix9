{
  mkDerivation,
  src,
  libauth,
  libauthsrv,
  libbio,
  libdisk,
  libip,
  libthread,
  autoDump ? true,
  dumpHour ? 5,
}:
assert builtins.isBool autoDump;
assert builtins.isInt dumpHour && dumpHour >= 0 && dumpHour <= 23;
mkDerivation {
  name = "cwfs64x";
  inherit src;
  buildInputs = [
    libauth
    libauthsrv
    libbio
    libdisk
    libip
    libthread
  ];
  buildPhase = ''
    sed 's/DUMPTIME = 5,/DUMPTIME = ${toString dumpHour},/' main.c > main.new
    mv main.new main.c
    sed 's/conf.nodump = 0;/conf.nodump = ${if autoDump then "0" else "1"};/' cwfs64x/conf.c > cwfs64x/conf.new
    mv cwfs64x/conf.new cwfs64x/conf.c
    cd cwfs64x
    objects=()
    for(file in 9p2 auth chk con config console cw data dentry fworm iobuf juke main malloc mworm net proc scsi sub time uidgid wren srv) {
      6c -I.. -o $file.6 ../$file.c
      objects=($objects $file.6)
    }
    6c -I.. '-DDATE=0' -o conf.6 conf.c
    6l -o cwfs64x $objects conf.6
    6c -I.. -o check.6 ${./check.c}
    6l -o cwfs-check check.6
  '';
  installPhase = ''
    mkdir -p $out/bin
    cp cwfs64x cwfs-check $out/bin/
  '';
}
