{ lib, config, ... }:
let
  inherit (lib) mkOption types;
  label = types.addCheck types.str (
    value:
    builtins.stringLength value <= 63 && builtins.match "[a-z0-9]([a-z0-9-]*[a-z0-9])?" value != null
  );
  inherit (import ../system/modules/types.nix { inherit lib; }) runtimeFile publicKeyPattern;
in
{
  options = {
    name = mkOption {
      type = label;
      default = "installation";
      description = "Installation name used for the manifest and build output.";
    };
    defaults = mkOption {
      default = { };
      description = "Discovery defaults. Provider names refer to machine inventory keys.";
      type = types.submodule {
        options =
          builtins.listToAttrs (
            map
              (
                name:
                lib.nameValuePair name (mkOption {
                  type = types.nullOr label;
                  default = null;
                  description = "Default ${name} provider.";
                })
              )
              [
                "auth"
                "fs"
                "cpu"
              ]
          )
          // {
            authdom = mkOption {
              type = types.nullOr (types.strMatching "[a-zA-Z0-9_.-]+");
              default = null;
              description = "Public authentication domain.";
            };
          };
      };
    };
    jobs = mkOption {
      default = { };
      description = "Scheduled jobs referring to machines in this installation.";
      type = types.attrsOf (
        types.submodule (
          { name, ... }: {
            options = (import ../system/modules/job.nix { inherit lib; }).options // {
              scheduler = mkOption {
                type = label;
                description = "Authentication server running cron.";
              };
              target = mkOption {
                type = label;
                description = "Machine running the command; remote targets must enable CPU access.";
              };
              keyPattern = mkOption {
                type = publicKeyPattern;
                description = "Public factotum attributes for remote CPU authentication.";
                default = if config.defaults.authdom == null then "" else "dom=${config.defaults.authdom}";
              };
            };
          }
        )
      );
    };
    machines = mkOption {
      description = "Machines, their advertised addresses and system modules.";
      type = types.attrsOf (
        types.submodule (
          { name, ... }: {
            options = {
              machineId = mkOption {
                type = label;
                default = name;
                description = "Stable provisioned identity, independent of the hostname.";
              };
              hostName = mkOption {
                type = label;
                default = name;
                description = "Hostname advertised in NDB.";
              };
              ip = mkOption {
                type = types.str;
                description = "IPv4 address advertised in NDB; native networking must make it reachable.";
              };
              configuration = mkOption {
                type = types.deferredModule;
                default = { };
                description = "Ordinary mkSystem module for this machine.";
              };
              mounts = mkOption {
                default = { };
                description = "Session mounts referring to exports in this installation.";
                type = types.attrsOf (
                  types.submodule (
                    { name, ... }: {
                      options = {
                        provider = mkOption {
                          type = label;
                          description = "Machine inventory key of the file provider.";
                        };
                        export = mkOption {
                          type = label;
                          default = name;
                          description = "Export declared on the provider.";
                        };
                        mountPoint = mkOption {
                          type = runtimeFile;
                          default = "/n/${name}";
                          description = "Existing directory where the share appears in the session.";
                        };
                        keyPattern = mkOption {
                          type = publicKeyPattern;
                          default = if config.defaults.authdom == null then "" else "dom=${config.defaults.authdom}";
                          description = "Public attributes selecting the client's factotum key.";
                        };
                        required = mkOption {
                          type = types.bool;
                          default = true;
                          description = "Fail session activation when this provider is unavailable.";
                        };
                        timeout = mkOption {
                          type = types.ints.between 1 300;
                          default = 10;
                          description = "Maximum seconds for authentication and mounting.";
                        };
                      };
                    }
                  )
                );
              };
            };
          }
        )
      );
    };
  };
}
