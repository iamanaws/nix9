{
  lib,
  runCommand,
  cTools,
  sysroot,
}:
{
  name,
  src,
  cFlags ? [ ],
}:
runCommand name
  {
    nativeBuildInputs = [ cTools ];
    ccroot = sysroot;
  }
  ''
    cp -r ${src} source
    chmod -R u+w source
    cd source
    sed -n '/^OFILES=/,/^$/p' mkfile | sed 's/\$objtype/amd64/g; s/^OFILES=//' | \
      sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.\$O.*/\1/p' > units
    test -s units
    while read -r unit; do
      6c -D_Noreturn= ${lib.escapeShellArgs cFlags} \
        -I ${sysroot}/amd64/include -I ${sysroot}/sys/include -o "$unit.6" "$unit.c"
    done < units
    9ar rcD ${name}.a ./*.6
    install -Dm644 ${name}.a "$out/lib/${name}.a"
  ''
