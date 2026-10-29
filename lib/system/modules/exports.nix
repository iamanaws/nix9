{ lib, ... }:
let
  inherit (import ./types.nix { inherit lib; }) userName runtimeFile publicKeyPattern;
in
{
  options.exports = lib.mkOption {
    default = { };
    description = "Existing directories served over authenticated TLS and 9P.";
    type = lib.types.attrsOf (
      lib.types.submodule {
        options = {
          path = lib.mkOption {
            type = runtimeFile;
            description = "Existing directory to export. Accounts and permissions are managed natively.";
          };
          port = lib.mkOption {
            type = lib.types.ints.between 1 65535;
            default = 17020;
            description = "TCP port dedicated to this export.";
          };
          readOnly = lib.mkOption {
            type = lib.types.bool;
            default = true;
            description = "Reject changes through this export, regardless of filesystem permissions.";
          };
          allowedUsers = lib.mkOption {
            type = lib.types.listOf userName;
            description = "Authenticated users allowed to access this export.";
          };
          keyFile = lib.mkOption {
            type = lib.types.nullOr runtimeFile;
            default = null;
            description = "Private runtime file of factotum key commands, loaded at server boot.";
          };
          keyPattern = lib.mkOption {
            type = publicKeyPattern;
            default = "";
            description = "Public attributes selecting the server's factotum key.";
          };
        };
      }
    );
  };
}
