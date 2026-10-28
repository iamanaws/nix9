{
  configuration,
  timesyncLogging,
  mkDerivation,
}:
(
  {
    enable ? false,
    files ? { },
  }:
  let
    error = message: throw "mkSystem: logging.${message}";
    validName =
      name: builtins.stringLength name <= 64 && builtins.match "[a-zA-Z0-9][a-zA-Z0-9_.-]*" name != null;
    mode = (
      {
        mode ? "0640",
      }:
      mode
    );
    validMode = value: builtins.isString value && builtins.match "0[2367][0-7][0-7]" value != null;
    declared = {
      nix9 = { };
    }
    // (if timesyncLogging then { timesync.mode = "0660"; } else { })
    // files;
    quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
    arguments = builtins.concatStringsSep " " (
      map (name: "${quote name} ${quote (mode declared.${name})}") (builtins.attrNames declared)
    );
    tool = mkDerivation {
      name = "nix9-log";
      buildCommand = ''
        mkdir -p $out/bin
        cp ${./log.c} log.c
        6c -o log.6 log.c
        6l -o $out/bin/nix9-log log.6
      '';
    };
  in
  if !builtins.isBool enable then
    error "enable must be a boolean"
  else if !builtins.isAttrs files || !builtins.all validName (builtins.attrNames files) then
    error "files must map log names of at most 64 letters, digits, dots, underscores or hyphens to settings; names must start with a letter or digit"
  else if
    !builtins.all (name: builtins.isAttrs files.${name} && validMode (mode files.${name})) (
      builtins.attrNames files
    )
  then
    error "files modes must be four-digit octal permission strings with owner write permission"
  else if !(enable || timesyncLogging) && files != { } then
    error "files requires logging.enable or services.timesync.logging"
  else if !(enable || timesyncLogging) then
    null
  else
    {
      prepare = ''
        # Preparation is machine-wide; checks must leave files untouched.
        if(~ $#nix9LogCheck 1 && ~ $nix9LogCheck 1) {
          ${tool}/bin/nix9-log check ${arguments}
        }
        if not {
          ${tool}/bin/nix9-log prepare ${arguments}
        }
      '';
      event = ''
        #!/bin/rc -e
        exec ${tool}/bin/nix9-log event $*
      '';
    }
)
  configuration
