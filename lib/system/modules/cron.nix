{ lib, ... }:
let
  job = import ./job.nix { inherit lib; };
in
{
  options.cron = {
    enable = lib.mkEnableOption "native scheduled jobs on the authentication server";
    keyFile = lib.mkOption {
      type = lib.types.nullOr (import ./types.nix { inherit lib; }).runtimeFile;
      default = null;
      description = "Private runtime file of factotum key commands, loaded at CPU boot. Null uses provisioned keys.";
    };
    jobs = lib.mkOption {
      default = { };
      description = "Scheduled rc commands. Remote job closures must also be installed on their target.";
      type = lib.types.attrsOf (
        lib.types.submodule {
          options = job.options // {
            target = lib.mkOption {
              type = lib.types.nullOr (lib.types.strMatching "[a-zA-Z0-9][a-zA-Z0-9_.-]*");
              default = null;
              description = "CPU hostname; null executes on this machine.";
            };
          };
        }
      );
    };
  };
}
