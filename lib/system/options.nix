{ lib, ... }:
let
  inherit (lib) mkOption types;
  settings =
    description:
    mkOption {
      type = types.attrsOf types.anything;
      default = { };
      inherit description;
    };
in
{
  options = {
    hostName = mkOption {
      type = types.str;
      description = "Machine hostname.";
    };
    machineId = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = "Expected provisioned machine identity, independent of the hostname.";
    };
    packages = mkOption {
      type = types.listOf types.package;
      default = [ ];
      description = "Packages available in system sessions.";
    };
    files = mkOption {
      type = types.attrsOf types.lines;
      default = { };
      description = "Text files under /cfg/nix9/files.";
    };
    webfs = settings "Certificate pin configuration.";
    networking = settings "Native Ethernet configuration.";
    logging = settings "Native log configuration.";
    services = mkOption {
      type = types.submodule {
        freeformType = types.attrsOf types.anything;
        imports = [
          ./modules/auth.nix
          ./modules/cpu.nix
        ];
      };
      default = { };
      description = "Native service configuration.";
    };
    assertions = mkOption {
      type = types.listOf (
        types.submodule {
          options = {
            assertion = mkOption { type = types.bool; };
            message = mkOption { type = types.str; };
          };
        }
      );
      default = [ ];
      description = "Configuration checks evaluated before building the system.";
    };
    warnings = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Configuration warnings.";
    };
  };
}
