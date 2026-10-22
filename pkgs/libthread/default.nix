{
  runCommand,
  cTools,
  sysroot,
  source,
}:
runCommand "9front-libthread"
  {
    nativeBuildInputs = [ cTools ];
    ccroot = sysroot;
  }
  ''
    cp -r ${source}/sys/src/libthread source
    chmod -R u+w source
    cd source
    sed -n '/^OFILES=/,/^$/p' mkfile | sed 's/\$objtype/amd64/g' | \
      sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.\$O.*/\1/p' > units
    test -s units
    while read -r unit; do
      # goken9cc lacks _Noreturn; -B permits paths ending in abort().
      6c -B -D_Noreturn= -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
        -o "$unit.6" "$unit.c"
    done < units
    9ar rc libthread.a ./*.6
    install -Dm644 libthread.a "$out/lib/libthread.a"
  ''
