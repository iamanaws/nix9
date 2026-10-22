{
  runCommand,
  cTools,
  sysroot,
  libc,
  libbio,
  libregexp,
  source,
}:
runCommand "mk"
  {
    nativeBuildInputs = [ cTools ];
    ccroot = sysroot;
  }
  ''
    cp -r ${source}/sys/src/cmd/mk source
    chmod -R u+w source
    cd source
    sed -n '/^OFILES=/,/^$/p' mkfile | sed 's/^OFILES=//' | \
      sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.\$O.*/\1/p' > units
    test -s units
    while read -r unit; do
      6c -B -D_Noreturn= -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
        -o "$unit.6" "$unit.c"
    done < units
    6l -H2 -L ${libc}/lib -L ${libbio}/lib -L ${libregexp}/lib -o mk ./*.6
    install -Dm755 mk "$out/bin/mk"
  ''
