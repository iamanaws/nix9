{ lib, ... }:
let
  inherit (import ./types.nix { inherit lib; }) userName runtimeFile;
in
{
  options.cpu = {
    enable = lib.mkEnableOption "authenticated remote CPU access";
    allowedUsers = lib.mkOption {
      type = lib.types.listOf userName;
      default = [ ];
      description = "Users allowed to execute commands after native authentication. Required when enabled.";
    };
    keyFile = lib.mkOption {
      type = lib.types.nullOr runtimeFile;
      default = null;
      description = "Private runtime file of factotum key commands, loaded at CPU boot. Null uses provisioned keys.";
    };
    keyPattern = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Public factotum key-selection attributes for the CPU server, such as dom and user.";
    };
  };
}
