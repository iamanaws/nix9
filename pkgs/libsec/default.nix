{
  runCommand,
  cTools,
  sysroot,
  source,
  mpc,
}:
runCommand "9front-libsec"
  {
    nativeBuildInputs = [
      cTools
      mpc
    ];
    ccroot = sysroot;
    passthru = { inherit source; };
  }
  ''
    cp -r ${source}/sys/src source
    chmod -R u+w source
    cd source/libsec
    for unit in secp256r1 secp384r1 secp256k1 jacobian; do
      (
        cd port
        printf '#include "os.h"\n#include <mp.h>\n' > "$unit.c"
        mpc "$unit.mp" >> "$unit.c"
      )
    done
    objectDir="$TMPDIR/sec-objects"
    mkdir "$objectDir"
    for part in port amd64; do
      (
        cd "$part"
        if [ "$part" = port ]; then
          sed -n '/^CFILES *=/,/^$/p' mkfile | tr '\\' ' ' | \
            grep -o '[a-zA-Z0-9_]*\.c' | sed 's/\.c$//' > "$TMPDIR/units"
        else
          sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.\$O.*/\1/p' mkfile > "$TMPDIR/units"
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
              -I ../../libmp/port -o "$objectDir/$unit.6" "$unit.c"
          fi
        done < "$TMPDIR/units"
      )
    done
    9ar rc "$TMPDIR/libsec.a" "$objectDir/"*.6
    install -Dm644 "$TMPDIR/libsec.a" "$out/lib/libsec.a"
  ''
