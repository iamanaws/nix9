{ stdenv }:
{
  name ? "shell",
  inputsFrom ? [ ],
  nativeBuildInputs ? [ ],
  buildInputs ? [ ],
  propagatedNativeBuildInputs ? [ ],
  propagatedBuildInputs ? [ ],
  shellHook ? "",
}@attrs:
let
  mergeInputs =
    name:
    (attrs.${name} or [ ])
    ++ builtins.filter (input: !(builtins.elem input inputsFrom)) (
      builtins.concatMap (input: input.${name} or [ ]) inputsFrom
    );
  inputs = {
    nativeBuildInputs = mergeInputs "nativeBuildInputs";
    buildInputs = mergeInputs "buildInputs";
    propagatedNativeBuildInputs = mergeInputs "propagatedNativeBuildInputs";
    propagatedBuildInputs = mergeInputs "propagatedBuildInputs";
  };
  hooks = builtins.concatStringsSep "\n" (
    builtins.foldl' (hooks: input: [ (input.shellHook or "") ] ++ hooks) [ ] inputsFrom ++ [ shellHook ]
  );
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
in
stdenv.mkDerivation {
  inherit name;
  inherit (inputs)
    nativeBuildInputs
    buildInputs
    propagatedNativeBuildInputs
    propagatedBuildInputs
    ;
  shellHook = hooks;
  buildCommand = ''
    mkdir -p $out
    echo ${quote ''
      #!${stdenv.shell}
      flag e +
      rfork ne
      tools=${quote stdenv.tools}
    ''} > $out/shell
    echo $__nix9ShellSetup >> $out/shell
    echo ${quote ''
      ${hooks}
      if(~ $#* 0) exec ${quote stdenv.shell} -m ${stdenv.tools}/rcmain -i
      if not exec ${quote stdenv.shell} -m ${stdenv.tools}/rcmain $*
    ''} >> $out/shell
    chmod +x $out/shell
  '';
}
