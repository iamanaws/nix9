{
  runCommand,
  gcc,
  cTools,
  sysroot,
  source,
}:
runCommand "9front-libbsd"
  {
    nativeBuildInputs = [
      gcc
      cTools
    ];
    ccroot = sysroot;
    passthru = { inherit source; };
  }
  ''
    cp -r ${source}/sys/src/ape/lib ape-lib
    chmod -R u+w ape-lib
    cd ape-lib/bsd
    source ${../../lib/ape-build.sh}
    # Follow the source image's member list rather than compiling stray files.
    sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.\$O.*/\1/p' mkfile > units
    test -s units
    mkdir "$TMPDIR/bsd-objects"
    while read -r unit; do
      apeCompile "$unit.c" "$TMPDIR/bsd-objects/$unit.6" c99 \
        -D_POSIX_SOURCE -D_BSD_EXTENSION -D_PLAN9_SOURCE -I ../ap/plan9
    done < units
    9ar rc "$TMPDIR/libbsd.a" "$TMPDIR/bsd-objects/"*.6
    install -Dm644 "$TMPDIR/libbsd.a" "$out/lib/libbsd.a"
  ''
