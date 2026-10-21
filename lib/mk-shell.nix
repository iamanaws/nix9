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
  inherit (stdenv) tools initialPath libc;
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
  script = ''
    #!/bin/rc
    flag e +
    rfork ne
    tools=${quote tools}
    $tools/bin/bind -b $tools/bin /bin
    ${import ./setup-environment.nix {
      inherit (inputs)
        nativeBuildInputs
        buildInputs
        propagatedNativeBuildInputs
        propagatedBuildInputs
        ;
      inherit initialPath libc;
      interactive = true;
    }}
    ${hooks}
    if(~ $#* 0) exec $tools/bin/rc -m $tools/rcmain -i
    if not exec $tools/bin/rc -m $tools/rcmain $*
  '';
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
    echo ${quote script} > $out/shell
    chmod +x $out/shell
  '';
}
