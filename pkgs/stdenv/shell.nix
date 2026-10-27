{
  lib,
  mkShell,
  writeText,
  writeShellScriptBin,
  bash,
  setup,
  shell,
  tools,
}:
{
  name ? "cross-shell",
  inputsFrom ? [ ],
  nativeBuildInputs ? [ ],
  buildInputs ? [ ],
  propagatedNativeBuildInputs ? [ ],
  propagatedBuildInputs ? [ ],
  shellHook ? "",
}:
let
  inputs =
    builtins.mapAttrs
      (
        name: values:
        values
        ++ builtins.filter (input: !(builtins.elem input inputsFrom)) (
          builtins.concatMap (input: input.${name} or [ ]) inputsFrom
        )
      )
      {
        inherit
          nativeBuildInputs
          buildInputs
          propagatedNativeBuildInputs
          propagatedBuildInputs
          ;
      };
  mk = writeShellScriptBin "mk" ''
    set -euo pipefail
    files=()
    args=()
    while (( $# )); do
      case "$1" in
        --) args+=("$@"); break ;;
        -f) files+=("''${2:?mk -f requires a file}"); shift 2 ;;
        -f?*) files+=("''${1#-f}"); shift ;;
        *) args+=("$1"); shift ;;
      esac
    done
    if (( ''${#files[@]} == 0 )); then files=(mkfile); fi
    mkWork=$(mktemp -d "$NIX9_ROOT/mk.XXXXXXXX")
    trap 'rm -rf "$mkWork"' EXIT
    flags=()
    for file in "''${files[@]}"; do
      adapted="$mkWork/mkfile.''${#flags[@]}"
      ${bash}/bin/bash ${./prepare-source.sh} --mkfile "$file" > "$adapted"
      flags+=(-f "$adapted")
    done
    ${tools}/bin/mk "''${flags[@]}" "''${args[@]}"
  '';
  environment = writeText "cross-shell.rc" ''
    tools=${tools}
    previousPath=$path
    ${setup (inputs // { interactive = true; })}
    path=(${mk}/bin $path $previousPath)
    CC=6c
    LD=6l
    AS=6a
    AR=ar
    exec ${bash}/bin/bash -c 'export -p'
  '';
in
mkShell {
  inherit name;
  shellHook = ''
    nix9CrossEnvironment=$(TMPDIR="$NIX_BUILD_TOP" ${shell} -e ${environment}) || exit $?
    eval "$nix9CrossEnvironment"
    unset nix9CrossEnvironment
    ${builtins.concatStringsSep "\n" (map (input: input.shellHook or "") (lib.reverseList inputsFrom))}
    ${shellHook}
  '';
}
// inputs
