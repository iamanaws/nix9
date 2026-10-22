{
  runCommand,
  plan9port,
  ed,
  cTools,
  sysroot,
  libc,
  libbio,
  source,
}:
runCommand "cc"
  {
    nativeBuildInputs = [
      cTools
      plan9port
    ];
    ccroot = sysroot;
  }
  ''
    cp -r ${source}/sys/src/cmd source
    chmod -R u+w source
    cd source
    (cd cc; 9 yacc -d cc.y)
    (cd 6a; 9 yacc -D1 -d a.y)
    rm -f 6c/enam.c
    (cd 6c; T=6 9 rc -c 'fn ed { ${ed}/bin/ed $* }; . ../cc/mkenam')
    test -s 6c/enam.c
    for command in cc 6c 6a 6l; do
      (
        cd "$command"
        sed -n '/^OFILES=/,/^$/p' mkfile | sed 's/^OFILES=//' | \
          sed -n 's/^[[:space:]]*\([a-zA-Z0-9_.]*\)\.\$O.*/\1/p' > units
        test -s units
        while read -r unit; do
          input="$unit.c"
          if ! test -f "$input"; then
            case "$unit" in
              enam) input=../6c/enam.c ;;
              *) input=../cc/$unit.c ;;
            esac
          fi
          6c -D_Noreturn= -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
            -o "$unit.6" "$input"
        done < units
        if test "$command" = cc; then
          9ar rcD cc.a6 ./*.6
        else
          set -- ./*.6
          if test "$command" = 6c; then
            set -- "$@" ../cc/cc.a6
          fi
          6l -H2 -L ${libc}/lib -L ${libbio}/lib -o "$command" "$@"
          install -Dm755 "$command" "$out/bin/$command"
        fi
      )
    done
  ''
