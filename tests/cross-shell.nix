{
  pkgs,
  mkShell,
  stdenvCross,
  libap,
  libbsd,
}:
let
  shell = mkShell {
    inputsFrom = [ stdenvCross ];
    buildInputs = [
      libap
      libbsd
    ];
  };
in
pkgs.runCommand "cross-shell-programs" { } ''
  expectedHome=$HOME
  ${shell.shellHook}
  ${pkgs.bash}/bin/bash ${./cross-shell.sh} ${../examples/hello} "$out" "$expectedHome" ${./stdenv-cross/main.c}
''
