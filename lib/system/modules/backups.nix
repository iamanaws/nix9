{ lib, ... }:
let
  label = lib.types.addCheck lib.types.str (
    value:
    builtins.stringLength value <= 63 && builtins.match "[a-z0-9]([a-z0-9-]*[a-z0-9])?" value != null
  );
  relative = lib.types.addCheck lib.types.str (
    value:
    builtins.match "[a-zA-Z0-9_+.-]+(/[a-zA-Z0-9_+.-]+)*" value != null
    && builtins.all (part: part != "." && part != ".." && part != "+") (lib.splitString "/" value)
  );
in
{
  options.backups = lib.mkOption {
    default = { };
    description = "Full archives of completed CWFS snapshots. Invoke through scheduled jobs or manually.";
    type = lib.types.attrsOf (
      lib.types.submodule {
        options = {
          sourceMount = lib.mkOption {
            type = label;
            description = "Managed native TCP mount with a dump attach.";
          };
          destinationMount = lib.mkOption {
            type = label;
            description = "Managed TLS directory export on independent backup storage.";
          };
          paths = lib.mkOption {
            type = lib.types.listOf relative;
            description = "Directories relative to the snapshot root, including their contents and metadata.";
          };
        };
      }
    );
  };
}
