{
  runCommand,
  cTools,
  sysroot,
  source,
}:
runCommand "9front-libmp"
  {
    nativeBuildInputs = [ cTools ];
    ccroot = sysroot;
    passthru = { inherit source; };
  }
  ''
    cp -r ${source}/sys/src/libmp libmp
    chmod -R u+w libmp
    cd libmp
    objectDir="$TMPDIR/mp-objects"
    mkdir "$objectDir"
    for part in port amd64; do
      (
        cd "$part"
        if [ "$part" = port ]; then
          sed -n '/^FILES=/,/^$/p' mkfile | \
            sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\\/\1/p' > "$TMPDIR/units"
        else
          sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.s.*/\1/p' mkfile > "$TMPDIR/units"
        fi
        test -s "$TMPDIR/units"
        while read -r unit; do
          if [ "$part" = port ] && [ -f "../amd64/$unit.s" ]; then
            continue
          fi
          if [ -f "$unit.s" ]; then
            6a -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
              -o "$objectDir/$unit.6" "$unit.s"
          else
            6c -D_Noreturn= -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
              -o "$objectDir/$unit.6" "$unit.c"
          fi
        done < "$TMPDIR/units"
      )
    done
    9ar rc "$TMPDIR/libmp.a" "$objectDir/"*.6
    install -Dm644 "$TMPDIR/libmp.a" "$out/lib/libmp.a"
  ''
