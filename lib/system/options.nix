{ lib, config, ... }:
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
  imports = [
    ./modules/directories.nix
    ./modules/builders.nix
    ./modules/session.nix
  ];
  config.logging = lib.mkMerge [
    (lib.mkIf config.services.cron.enable {
      enable = lib.mkDefault true;
      files.cron.mode = lib.mkDefault "0660";
    })
    (lib.mkIf config.services.cwfs.enable {
      enable = lib.mkDefault true;
      files.cwfs.mode = lib.mkDefault "0640";
    })
  ];
  config.directories = lib.mkMerge (
    map (user: {
      "/sys/log/nix9-jobs/${user}" = {
        mode = lib.mkDefault "0700";
        owner = lib.mkDefault user;
      };
    }) (lib.unique (map (job: job.user) (builtins.attrValues config.services.cron.jobs)))
    ++ lib.optional config.services.cron.enable { "/cron".mode = lib.mkDefault "0775"; }
  );
  options = {
    namespace = lib.mkOption {
      type = lib.types.submodule { imports = [ ./modules/namespace.nix ]; };
      default = { };
      description = "User session namespace configuration.";
    };
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
    networking = mkOption {
      type = types.submodule { imports = [ ./modules/networking.nix ]; };
      default = { };
      description = "Native Ethernet configuration.";
    };
    logging = settings "Native log configuration.";
    services = mkOption {
      type = types.submodule {
        freeformType = types.attrsOf types.anything;
        imports = [
          ./modules/auth.nix
          ./modules/cpu.nix
          ./modules/exports.nix
          ./modules/cron.nix
          ./modules/cwfs.nix
          ./modules/backups.nix
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
