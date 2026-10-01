{
  pkgs,
  cTools,
  sysroot,
  libc,
}:
{
  name,
  sources,
  includeDirs ? [ ],
  libraries ? [ ],
  meta ? { },
}:
let
  inherit (pkgs) lib;
  units = lib.imap0 (index: source: {
    inherit source;
    object = "unit-${toString index}.6";
  }) sources;
  includes = lib.concatMapStringsSep " " (dir: "-I ${lib.escapeShellArg "${dir}"}") (
    [
      "${sysroot}/amd64/include"
      "${sysroot}/sys/include"
    ]
    ++ includeDirs
  );
in
assert builtins.match "[a-zA-Z0-9][a-zA-Z0-9._+-]*" name != null;
assert sources != [ ];
pkgs.runCommand name
  {
    nativeBuildInputs = [
      cTools
      pkgs.go
    ];
    ccroot = sysroot;
    inherit meta;
  }
  ''
    ${lib.concatMapStringsSep "\n" (unit: ''
      6c -D_Noreturn= ${includes} -o ${unit.object} ${lib.escapeShellArg "${unit.source}"}
    '') units}
    6l -H2 -L ${libc}/lib ${
      lib.concatMapStringsSep " " (library: "-L ${lib.escapeShellArg "${library}/lib"}") libraries
    } \
      -o program ${lib.concatMapStringsSep " " (unit: unit.object) units}
    export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache" GOPROXY=off GOTOOLCHAIN=local
    go run ${../tests/format.go} program
    install -Dm755 program "$out/bin/${name}"
  ''
