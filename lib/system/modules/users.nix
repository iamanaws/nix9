{ lib }:
let
  inherit (import ./types.nix { inherit lib; }) runtimeFile;
in
lib.types.attrsOf (
  lib.types.submodule (
    { name, ... }: {
      options = {
        id = lib.mkOption {
          type = lib.types.ints.between 1 32767;
          description = "Stable on-disk CWFS identity. Changing an existing name's ID is rejected.";
        };
        leader = lib.mkOption {
          type = lib.types.nullOr (lib.types.strMatching "[a-zA-Z0-9][a-zA-Z0-9_.]*");
          default = name;
          description = "Native group leader; null lets any member lead the group.";
        };
        members = lib.mkOption {
          type = lib.types.listOf (lib.types.strMatching "[a-zA-Z0-9][a-zA-Z0-9_.]*");
          default = [ ];
          description = "Complete native group membership for this declared entry.";
        };
        home = lib.mkOption {
          type = lib.types.nullOr runtimeFile;
          default = null;
          description = "Optional home directory in the CWFS main tree, owned by this identity.";
        };
        homeMode = lib.mkOption {
          type = lib.types.strMatching "0[0-7][0-7][0-7]";
          default = "0700";
          description = "Permission bits for the declared home directory.";
        };
      };
    }
  )
)
