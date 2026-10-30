{ lib, ... }:
let
  inherit (import ./types.nix { inherit lib; }) runtimeFile publicKeyPattern;
in
{
  options.binds = lib.mkOption {
    default = [ ];
    description = "Directory bindings applied in list order after session shares.";
    type = lib.types.listOf (
      lib.types.submodule {
        options = {
          source = lib.mkOption {
            type = lib.types.addCheck lib.types.str (
              value:
              builtins.match "/[a-zA-Z0-9_+.-]+(/[a-zA-Z0-9_+.-]+)*" value != null
              && builtins.all (part: part != "." && part != "..") (lib.splitString "/" value)
              && (
                !(lib.hasPrefix "/usr/local/nix/store" value || lib.hasPrefix "/nix/store" value)
                || builtins.hasContext value
              )
            );
            description = "Existing source directory, optionally a package output with its Nix reference.";
          };
          target = lib.mkOption {
            type = runtimeFile;
            description = "Destination directory, supplied by the filesystem or directories declaration.";
          };
          mode = lib.mkOption {
            type = lib.types.enum [
              "replace"
              "prepend"
              "append"
            ];
            default = "replace";
            description = "Replace the destination view or add the source before/after its entries.";
          };
          create = lib.mkOption {
            type = lib.types.bool;
            default = false;
            description = "Permit new files to be created through this union entry, within native permissions.";
          };
          required = lib.mkOption {
            type = lib.types.bool;
            default = true;
            description = "Fail refresh when the source is unavailable; false skips that entry.";
          };
        };
      }
    );
  };
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
