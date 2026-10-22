{
  stdenv,
  src,
  buildPackages,
  libbio,
  libregexp,
  libString,
  libflate,
}:
let
  commands = import ./commands.nix;
in
stdenv.mkDerivation {
  name = "build-tools";
  cputype = "amd64";
  inherit src;
  patches = [ ./awk-maketab.patch ];
  passthru = { inherit commands; };
  nativeBuildInputs = [
    buildPackages.yacc
    buildPackages.awkMaketab
  ];
  buildInputs = [
    libbio
    libregexp
    libString
    libflate
  ];
  sourceRoot = "source/sys/src";
  buildPhase = ''
    commands=( ${builtins.concatStringsSep " " commands} )
    cd cmd
    for(command in $commands) {
      6c -FTVw $command^.c
      6l -o $command $command^.6
    }
    @{ cd gzip; 6c gunzip.c; 6l -o gunzip gunzip.6 }
    @{ cd grep; mk }
    @{
      cd awk
      rm -f awkgram.c y.tab.h proctab.c
      yacc -d -o awkgram.c awkgram.y
      mk 'MAKETAB=${buildPackages.awkMaketab}/bin/maketab'
    }
  '';
  installPhase = ''
    mkdir -p $out/bin
    for(command in $commands) cp $command $out/bin/$command
    cp gzip/gunzip $out/bin/gunzip
    cp grep/6.out $out/bin/grep
    cp awk/6.out $out/bin/awk
  '';
}
