{
  runCommand,
  gcc,
  cTools,
  sysroot,
  source,
}:
runCommand "9front-libap"
  {
    nativeBuildInputs = [
      gcc
      cTools
    ];
    ccroot = sysroot;
    passthru = { inherit source; };
  }
  ''
    cp -r ${source}/sys source-sys
    chmod -R u+w source-sys
    cd source-sys/src/ape/lib/ap
    substituteInPlace plan9/{getpid,profile}.c \
      --replace-fail '"/sys/include/tos.h"' '"${sysroot}/sys/include/tos.h"'
    apeRoot="$PWD"
    objectDir="$TMPDIR/ap-objects"
    mkdir "$objectDir"
    source ${../../lib/ape-build.sh}
    for part in gen math plan9 posix stdio amd64; do
      (
        cd "$part"
        sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.\$O.*/\1/p' mkfile > "$TMPDIR/units"
        test -s "$TMPDIR/units"
        flags=(-D_POSIX_SOURCE)
        case "$part" in
          plan9) flags+=(-D_PLAN9_SOURCE -D_BSD_EXTENSION);;
          amd64) flags+=(-D_PLAN9_SOURCE);;
        esac
        while read -r unit; do
          # gen/reduce excludes functions supplied by the machine directory.
          if [ "$part" = gen ] && { [ -f "../amd64/$unit.c" ] || [ -f "../amd64/$unit.s" ]; }; then
            continue
          fi
          if [ -f "$unit.s" ]; then
            6a -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
              -o "$objectDir/$unit.6" "$unit.s"
          else
            apeCompile "$unit.c" "$objectDir/$unit.6" c99 "''${flags[@]}"
          fi
        done < "$TMPDIR/units"
      )
    done
    # The amd64 syscall template from libc/9syscall/mkfile, with APE names.
    mkdir "$TMPDIR/syscalls"
    cd "$TMPDIR/syscalls"
    awk '$1 == "#define" && $2 ~ /^[A-Z][A-Z0-9_]*$/ {
      name = "_" $2
      symbol = ($2 == "SEEK" ? "__SEEK" : name)
      printf "TEXT %s(SB), 1, $0\nMOVQ RARG, a0+0(FP)\nMOVQ $%s, RARG\nSYSCALL\nRET\n", symbol, $3 > name ".s"
    }' "$apeRoot/../../../libc/9syscall/sys.h"
    for stub in *.s; do
      6a -o "$objectDir/''${stub%.s}.6" "$stub"
    done
    9ar rc "$TMPDIR/libap.a" "$objectDir/"*.6
    install -Dm644 "$TMPDIR/libap.a" "$out/lib/libap.a"
  ''
