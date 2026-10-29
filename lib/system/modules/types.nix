{ lib }:
{
  userName = lib.types.addCheck lib.types.str (
    value: builtins.stringLength value < 28 && builtins.match "[a-zA-Z0-9][a-zA-Z0-9_.-]*" value != null
  );
  runtimeFile = lib.types.addCheck lib.types.str (
    value:
    !builtins.hasContext value
    && builtins.match "/[a-zA-Z0-9_+.-]+(/[a-zA-Z0-9_+.-]+)*" value != null
    && builtins.all (part: part != "." && part != "..") (lib.splitString "/" value)
    && !lib.hasPrefix "/usr/local/nix/store" value
    && !lib.hasPrefix "/nix/store" value
  );
}
