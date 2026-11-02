{ lib, ... }:
let
  inherit (lib) mkOption types;
  inherit (import ./types.nix { inherit lib; }) runtimeFile;
in
{
  options.tftpd = mkOption {
    default = { };
    description = "Native TFTP serving of public boot files.";
    type = types.submodule {
      options = {
        enable = lib.mkEnableOption "native TFTP serving";
        directory = mkOption {
          type = runtimeFile;
          default = "/lib/tftp";
          description = "Public file directory. Inventory boot artifacts publish immutable versions and select configurations here.";
        };
      };
    };
  };
}
