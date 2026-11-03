{ lib, ... }:
let
  inherit (import ./types.nix { inherit lib; }) userName runtimeFile publicKeyPattern;
in
{
  options.nixStore = {
    enable = lib.mkEnableOption "an authenticated shared Nix store on this CPU server";
    allowedUsers = lib.mkOption {
      type = lib.types.listOf userName;
      default = [ ];
      description = "Users allowed to build packages and manage their own roots and profiles. Required when enabled; none is reserved for builds.";
    };
    port = lib.mkOption {
      type = lib.types.ints.between 1 65535;
      default = 17051;
      description = "TCP port on the loopback interface. Changes take effect after reboot.";
    };
    keyFile = lib.mkOption {
      type = lib.types.nullOr runtimeFile;
      default = null;
      description = "Private runtime file of factotum key commands, loaded at CPU boot. Null uses provisioned keys.";
    };
    keyPattern = lib.mkOption {
      type = publicKeyPattern;
      default = "";
      description = "Public factotum key-selection attributes for the store server, such as dom and user.";
    };
  };
}
