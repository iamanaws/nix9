{
  stdenv,
  src,
  libc,
  libbio,
  libstdio,
  yacc,
}:
stdenv.mkDerivation {
  name = "cc";
  timezone = "GMT 0 GMT 0\n";
  inherit src;
  sourceRoot = "source/sys/src/cmd";
  nativeBuildInputs = [ yacc ];
  buildInputs = [
    libc
    libbio
    libstdio
  ];
  postUnpack = "rm -f 6c/enam.c";
  buildPhase = ''
    @{ cd cc; mk install }
    for(command in 6c 6a 6l cpp) @{ cd $command; mk }
    6c -FTVw pcc.c
    6l -o pcc pcc.6
  '';
  installPhase = ''
    mkdir -p $out/bin
    for(command in 6c 6a 6l cpp) cp $command/6.out $out/bin/$command
    cp pcc $out/bin/pcc
  '';
  meta.description = "Plan 9 and APE C toolchain";
}
