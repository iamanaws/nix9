{
  runCommand,
  plan9port,
  binutils,
  source,
}:
runCommand "build-awk-maketab"
  {
    nativeBuildInputs = [
      plan9port
      binutils
    ];
  }
  ''
    cp -r ${source}/sys/src/cmd/awk .
    chmod -R u+w awk
    cd awk
    9 yacc -d -o awkgram.c awkgram.y
    9 9c maketab.c
    9 9l -o maketab maketab.o
    install -Dm755 maketab "$out/bin/maketab"
  ''
