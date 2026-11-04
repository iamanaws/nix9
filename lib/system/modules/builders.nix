{
  lib,
  pkgs,
  config,
  ...
}:
let
  configuration = config.nix;
  explicitBuilders = configuration.settings.builders or null;
  field = values: if values == [ ] then "-" else lib.concatStringsSep "," values;
  builderLine =
    builder:
    lib.concatStringsSep " " [
      (
        builder.protocol
        + "://"
        + lib.optionalString (builder.user != null) (builder.user + "@")
        + builder.hostName
        + lib.optionalString (builder.keyPattern != "") ("?key-pattern=" + lib.escapeURL builder.keyPattern)
      )
      (field (if builder.system != null then [ builder.system ] else builder.systems))
      "-"
      (toString builder.maxJobs)
      (toString builder.speedFactor)
      (field (lib.unique (builder.supportedFeatures ++ builder.mandatoryFeatures)))
      (field builder.mandatoryFeatures)
    ];
in
{
  options.nix = {
    distributedBuilds = lib.mkEnableOption "distributed Nix builds on the declared build machines";
    buildMachines = lib.mkOption {
      default = [ ];
      description = "Remote Nix builders reached through authenticated CPU sessions.";
      type = lib.types.listOf (
        lib.types.submodule {
          options = (import ./builder.nix { inherit lib; }) // {
            hostName = lib.mkOption {
              type = lib.types.strMatching "[a-zA-Z0-9][a-zA-Z0-9_.-]*";
              description = "CPU server hostname or IPv4 address.";
            };
            protocol = lib.mkOption {
              type = lib.types.enum [ "cpu" ];
              default = "cpu";
              description = "Native authenticated CPU transport. SSH transports are not ported.";
            };
          };
        }
      );
    };
  };
  config = {
    packages = lib.optional (
      configuration.buildMachines != [ ] || (explicitBuilders != null && explicitBuilders != "")
    ) pkgs.rcpu;
    nix.settings.builders = lib.mkDefault (
      if configuration.distributedBuilds then
        lib.concatMapStringsSep " ; " builderLine configuration.buildMachines
      else
        ""
    );
    assertions = [
      {
        assertion = builtins.deepSeq configuration.buildMachines (
          builtins.all (builder: builder.system != null || builder.systems != [ ]) configuration.buildMachines
        );
        message = "nix.buildMachines requires system or a nonempty systems list for each builder";
      }
    ];
  };
}
