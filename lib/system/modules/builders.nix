{
  lib,
  pkgs,
  config,
  ...
}:
let
  configuration = config.nix;
  field = values: if values == [ ] then "-" else lib.concatStringsSep "," values;
  builderLine =
    _: builder:
    lib.concatStringsSep " " [
      (
        "cpu://"
        + lib.optionalString (builder.user != null) (builder.user + "@")
        + builder.host
        + lib.optionalString (builder.keyPattern != "") ("?key-pattern=" + lib.escapeURL builder.keyPattern)
      )
      (field builder.systems)
      "-"
      (toString builder.maxJobs)
      (toString builder.speedFactor)
      (field builder.supportedFeatures)
      (field builder.mandatoryFeatures)
    ];
  configured =
    configuration.builders != { }
    || configuration.maxJobs != null
    || configuration.systemFeatures != [ ];
in
{
  options.nix = {
    builders = lib.mkOption {
      default = { };
      description = "Remote Nix builders reached through authenticated CPU sessions.";
      type = lib.types.attrsOf (
        lib.types.submodule {
          options = (import ./builder.nix { inherit lib; }) // {
            host = lib.mkOption {
              type = lib.types.strMatching "[a-zA-Z0-9][a-zA-Z0-9_.-]*";
              description = "CPU server hostname or IPv4 address.";
            };
          };
        }
      );
    };
    maxJobs = lib.mkOption {
      type = lib.types.nullOr lib.types.ints.unsigned;
      default = null;
      description = "Concurrent local builds; zero requires a remote builder. Null uses Nix's default.";
    };
    systemFeatures = lib.mkOption {
      type = lib.types.listOf (lib.types.strMatching "[a-zA-Z0-9_+.-]+");
      default = [ ];
      description = "System features available to builds on this machine.";
    };
  };
  config = lib.mkIf configured {
    packages = lib.optional (configuration.builders != { }) pkgs.rcpu;
    files."nix.conf" =
      "builders = "
      + lib.concatStringsSep " ; " (lib.mapAttrsToList builderLine configuration.builders)
      + "\n"
      + lib.optionalString (
        configuration.maxJobs != null
      ) "max-jobs = ${toString configuration.maxJobs}\n"
      + lib.optionalString (
        configuration.systemFeatures != [ ]
      ) "system-features = ${lib.concatStringsSep " " configuration.systemFeatures}\n";
  };
}
