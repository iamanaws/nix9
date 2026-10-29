{
  lib ? (import <nix9>).lib,
  scenario ? "valid",
}:
let
  evaluation = lib.evalModules {
    modules = [
      {
        options = {
          message = lib.mkOption { type = lib.types.str; };
          enabled = lib.mkOption {
            type = lib.types.bool;
            default = false;
          };
          order = lib.mkOption {
            type = lib.types.listOf lib.types.str;
            default = [ ];
          };
          conditional = lib.mkOption {
            type = lib.types.str;
            default = "disabled";
          };
        };
        config.message = lib.mkDefault "default";
      }
      ./module-import.nix
      ({ config, ... }: {
        config = lib.mkMerge [
          {
            message = lib.mkForce "forced";
            enabled = true;
            order = lib.mkBefore [ "first" ];
          }
          (lib.mkIf config.enabled { conditional = "enabled"; })
        ];
      })
      (
        if scenario == "invalid-type" then
          { enabled = "yes"; }
        else if scenario == "unknown-option" then
          { missing = true; }
        else
          { }
      )
    ];
  };
in
evaluation.config
