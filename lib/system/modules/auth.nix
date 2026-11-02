{ lib, ... }:
let
  inherit (import ./types.nix { inherit lib; }) userName runtimeFile;
in
{
  options.auth = {
    requiredUsers = lib.mkOption {
      type = lib.types.listOf userName;
      default = [ ];
      description = "Provisioned identities that must have enabled, unexpired dp9ik keys. Keys are checked without changing the authentication database.";
    };
    enable = lib.mkEnableOption "the native authentication ticket service";
    keyDatabase = lib.mkOption {
      type = runtimeFile;
      default = "/adm/keys";
      description = "Existing private authentication database, decrypted with the machine's provisioned NVRAM key.";
    };
    speaksFor = lib.mkOption {
      type = lib.types.attrsOf (lib.types.listOf userName);
      default = { };
      description = "Authentication identities and the users they may represent. Self-authentication remains allowed.";
    };
  };
}
