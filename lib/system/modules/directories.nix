{ lib, ... }:
let
  inherit (import ./types.nix { inherit lib; }) userName;
in
{
  options.directories = lib.mkOption {
    default = { };
    description = "Persistent directories prepared at selection and boot. Contents are preserved.";
    type = lib.types.attrsOf (
      lib.types.submodule {
        options = {
          mode = lib.mkOption {
            type = lib.types.addCheck lib.types.str (value: builtins.match "0[0-7][0-7][0-7]" value != null);
            default = "0755";
            description = "Directory permission bits, as a four-digit octal string.";
          };
          owner = lib.mkOption {
            type = lib.types.nullOr userName;
            default = null;
            description = "Native file owner. Null preserves the existing owner or uses the creator for a new directory.";
          };
          group = lib.mkOption {
            type = lib.types.nullOr userName;
            default = null;
            description = "Native file group. Null preserves the existing group or inherits the parent's group on creation.";
          };
        };
      }
    );
  };
}
