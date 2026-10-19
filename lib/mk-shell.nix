{ mkDerivation, tools }:
{
  name ? "shell",
  nativeBuildInputs ? [ ],
  buildInputs ? [ ],
  shellHook ? "",
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
  script = ''
    #!/bin/rc
    flag e +
    rfork ne
    tools=${quote tools}
    $tools/bin/bind -b $tools/bin /bin
    ${import ./setup-environment.nix {
      inherit nativeBuildInputs buildInputs;
      interactive = true;
    }}
    ${shellHook}
    if(~ $#* 0) exec $tools/bin/rc -m $tools/rcmain -i
    if not exec $tools/bin/rc -m $tools/rcmain $*
  '';
in
mkDerivation {
  inherit name;
  buildCommand = ''
    mkdir -p $out
    echo ${quote script} > $out/shell
    chmod +x $out/shell
  '';
}
