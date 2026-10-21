{
  stdenv,
  src,
  libc,
  libbio,
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
  ];
  postUnpack = "rm -f 6c/enam.c";
  buildPhase = ''
    @{ cd cc; mk install }
    for(command in 6c 6a 6l) @{ cd $command; mk }
  '';
  installPhase = ''
    mkdir -p $out/bin
    for(command in 6c 6a 6l) cp $command/6.out $out/bin/$command
  '';
  meta.description = "Plan 9 C compiler, assembler and linker";
}
