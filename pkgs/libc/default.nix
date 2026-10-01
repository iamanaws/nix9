{
  runCommand,
  cTools,
  sysroot,
  source,
}:
runCommand "9front-libc"
  {
    nativeBuildInputs = [ cTools ];
    ccroot = sysroot;
    passthru = { inherit source; };
  }
  ''
    cp -r ${source}/sys/src/libc libc
    chmod -R u+w libc
    cd libc
    libcRoot="$PWD"
    objectDir="$TMPDIR/libc-objects"
    mkdir "$objectDir"
    for part in 9sys fmt port amd64 ucd; do
      (
        cd "$part"
        sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.\(\$O\|c\|s\).*/\1/p' mkfile > "$TMPDIR/units"
        test -s "$TMPDIR/units"
        while read -r unit; do
          # port/reduce excludes functions supplied by the machine directory.
          if [ "$part" = port ] && { [ -f "../amd64/$unit.c" ] || [ -f "../amd64/$unit.s" ]; }; then
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
    # Match the amd64 syscall recipe, retaining the historical entry points.
    mkdir "$TMPDIR/syscalls"
    cd "$TMPDIR/syscalls"
    awk '$1 == "#define" && $2 !~ /^_X[123]/ {
      name = tolower($2)
      if (name == "exits" || name == "nsec") name = "_" name
      symbol = (name == "seek" ? "_seek" : name)
      printf "TEXT %s(SB), 1, $0\nMOVQ RARG, a0+0(FP)\nMOVQ $%s, RARG\nSYSCALL\nRET\n", symbol, $3 > name ".s"
    }' "$libcRoot/9syscall/sys.h"
    for stub in *.s; do
      6a -o "$objectDir/''${stub%.s}.6" "$stub"
    done
    9ar rc "$TMPDIR/libc.a" "$objectDir/"*.6
    install -Dm644 "$TMPDIR/libc.a" "$out/lib/libc.a"
  ''
