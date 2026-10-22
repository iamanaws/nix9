{
  runCommand,
  plan9port,
  cTools,
  sysroot,
  libc,
  source,
}:
runCommand "rc"
  {
    nativeBuildInputs = [
      cTools
      plan9port
    ];
    ccroot = sysroot;
  }
  ''
    cp -r ${source}/sys/src/cmd/rc source
    chmod -R u+w source
    cd source
    9 yacc -d syn.y
    sed -n '/^OFILES=/,/^$/p' mkfile | sed 's/^OFILES=//' | \
      sed -n 's/^[[:space:]]*\([a-zA-Z0-9_.]*\)\.\$O.*/\1/p' > units
    test -s units
    while read -r unit; do
      6c -DPlan9 -D_Noreturn= -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
        -o "$unit.6" "$unit.c"
    done < units
    6l -H2 -L ${libc}/lib -o rc ./*.6
    install -Dm755 rc "$out/bin/rc"
  ''
