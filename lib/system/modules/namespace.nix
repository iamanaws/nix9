{ lib, ... }:
let
  inherit (import ./types.nix { inherit lib; }) runtimeFile publicKeyPattern;
in
{
  options.mounts = lib.mkOption {
    default = { };
    description = "Authenticated file shares mounted in user sessions.";
    type = lib.types.attrsOf (
      lib.types.submodule (
        { name, ... }: {
          options = {
            address = lib.mkOption {
              type = lib.types.strMatching "(tcp|net)![a-zA-Z0-9_.:-]+![a-zA-Z0-9-]+";
              description = "Native dial address, including the export's TCP service or port.";
            };
            mountPoint = lib.mkOption {
              type = runtimeFile;
              default = "/n/${name}";
              description = "Existing directory where the share appears in this session.";
            };
            keyPattern = lib.mkOption {
              type = publicKeyPattern;
              default = "";
              description = "Public attributes selecting the client's factotum key.";
            };
            required = lib.mkOption {
              type = lib.types.bool;
              default = true;
              description = "Fail session activation if the share cannot be mounted.";
            };
            timeout = lib.mkOption {
              type = lib.types.ints.between 1 300;
              default = 10;
              description = "Maximum seconds for authentication and mounting.";
            };
          };
        }
      )
    );
  };
}
