{
  stdenv,
  src,
  yacc,
  libbio,
  libregexp,
}:
let
  commands = import ./commands.nix;
in
stdenv.mkDerivation {
  name = "build-tools";
  cputype = "amd64";
  inherit src;
  passthru = { inherit commands; };
  nativeBuildInputs = [ yacc ];
  buildInputs = [
    libbio
    libregexp
  ];
  sourceRoot = "source/sys/src";
  buildPhase = ''
    commands=( ${builtins.concatStringsSep " " commands} )
    mkdir lib
    for(library in libString libflate) @{
      cd $library
      mk 'LIB='$library^.a
      cp $library^.a ../lib/
    }
    bind -b `{pwd}^/lib /amd64/lib
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
      mk
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
