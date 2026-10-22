{
  runCommand,
  lib,
  plan9port,
  binutils,
  cTools,
  sysroot,
  libc,
  libbio,
  libregexp,
  mkPlan9Library,
  source,
}:
let
  libraries =
    map
      (
        name:
        mkPlan9Library {
          inherit name;
          src = "${source}/sys/src/${name}";
          cFlags = [ "-B" ];
        }
      )
      [
        "libString"
        "libflate"
      ];
in
runCommand "build-tools"
  {
    nativeBuildInputs = [
      cTools
      plan9port
      binutils
    ];
    ccroot = sysroot;
  }
  ''
    cp -r ${source}/sys/src source
    chmod -R u+w source
    cd source/cmd
    compile() {
      6c -B -D_Noreturn= -I ${sysroot}/amd64/include -I ${sysroot}/sys/include -o "$1.6" "$1.c"
    }
    link() {
      name="$1"
      shift
      6l -H2 -L ${libc}/lib -L ${libbio}/lib -L ${libregexp}/lib \
        ${lib.concatMapStringsSep " " (library: "-L ${library}/lib") libraries} -o "$name" "$@"
      install -Dm755 "$name" "$out/bin/$name"
    }
    for command in ${lib.escapeShellArgs (import ./commands.nix)}; do
      compile "$command"
      link "$command" "$command.6"
    done
    (cd gzip; compile gunzip; link gunzip gunzip.6)
    (
      cd grep
      9 yacc -d grep.y
      for unit in y.tab main comp sub; do compile "$unit"; done
      link grep ./*.6
    )
    (
      cd awk
      rm -f awkgram.c y.tab.h proctab.c
      9 yacc -d -o awkgram.c awkgram.y
      9 9c maketab.c
      9 9l -o maketab maketab.o
      ./maketab > proctab.c
      sed -n '/^OFILES=/,/^$/p' mkfile | sed 's/^OFILES=//' | \
        sed -n 's/^[[:space:]]*\([a-zA-Z0-9_]*\)\.\$O.*/\1/p' > units
      while read -r unit; do compile "$unit"; done < units
      link awk ./*.6
    )
  ''
