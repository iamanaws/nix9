{
  runCommand,
  plan9port,
  binutils,
  source,
}:
runCommand "9front-unicode-tables"
  {
    nativeBuildInputs = [
      plan9port
      binutils
    ];
  }
  ''
    cp ${source}/sys/src/libc/ucd/mkrunetype.c .
    chmod u+w mkrunetype.c
    substituteInPlace mkrunetype.c --replace-fail '"/lib/ucd/' '"${source}/lib/ucd/'
    9 9c mkrunetype.c
    9 9l -o mkrunetype mkrunetype.o
    ./mkrunetype
    # Reference tables from the pinned test image.
    sha256sum -c ${../../tests/libc-tables.sha256}
    mkdir "$out"
    cp rune*data "$out/"
  ''
