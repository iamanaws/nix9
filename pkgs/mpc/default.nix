{
  runCommand,
  plan9port,
  mkPlan9Program,
  libbio,
  libmp,
  source,
}:
let
  parser = runCommand "mpc-parser.c" { nativeBuildInputs = [ plan9port ]; } ''
    9 yacc ${source}/sys/src/cmd/mpc.y
    cp y.tab.c "$out"
  '';
in
mkPlan9Program {
  name = "mpc";
  sources = [ parser ];
  libraries = [
    libmp
    libbio
  ];
}
