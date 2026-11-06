{ lib, config, ... }:
let
  inherit (lib) mkOption types;
  inherit (import ./types.nix { inherit lib; }) userName;
  cfg = config.nix;
  atom = types.oneOf [
    types.bool
    types.int
    types.float
    types.str
    types.path
  ];
  value = types.nullOr (types.either atom (types.listOf atom));
  renderAtom = item: if builtins.isBool item then lib.boolToString item else toString item;
  renderValue =
    item: if builtins.isList item then lib.concatMapStringsSep " " renderAtom item else renderAtom item;
  settings = lib.filterAttrs (_: item: item != null) cfg.settings;
  text = lib.concatStrings (
    lib.mapAttrsToList (name: item: "${name} = ${renderValue item}\n") settings
  );
in
{
  imports = [
    ./nix-daemon.nix
    ./builders.nix
  ];
  options.nix.settings = mkOption {
    default = { };
    description = "Nix settings written to nix.conf. Shared-store workers read the booted configuration.";
    type = types.submodule {
      freeformType = types.attrsOf value;
      options = {
        allowed-users = mkOption {
          type = types.listOf types.str;
          default = [ "*" ];
          description = "Authenticated users allowed to use the daemon. * allows all except the anonymous build identity none; trusted users are also allowed. Group selectors are not yet supported.";
        };
        trusted-users = mkOption {
          type = types.listOf types.str;
          default = [ ];
          description = "Authenticated users with privileged daemon access, including remote input-addressed builds and daemon setting overrides. Empty by default. Group selectors are not yet supported.";
        };
        max-jobs = mkOption {
          type = types.either types.ints.unsigned (types.enum [ "auto" ]);
          default = 1;
          description = "Maximum concurrent local builds; zero requires a remote builder. Shared local builds are additionally serialized by the native backend.";
        };
        system-features = mkOption {
          type = types.listOf (types.strMatching "[a-zA-Z0-9_+.-]+");
          default = [ ];
          description = "Features this machine provides to Nix builds.";
        };
      };
    };
  };
  config = {
    files."nix.conf" = text;
    assertions = [
      {
        assertion =
          builtins.all (name: builtins.match "[a-zA-Z][a-zA-Z0-9_-]*" name != null) (
            builtins.attrNames settings
          )
          && builtins.all (item: builtins.match ".*[\r\n#].*" (renderValue item) == null) (
            builtins.attrValues settings
          );
        message = "nix.settings requires setting names and single-line values without # comments";
      }
      {
        assertion = builtins.all (
          user: user == "*" || (userName.check user && user != "none")
        ) cfg.settings.allowed-users;
        message = "nix.settings.allowed-users accepts native usernames or *; @group selectors and the anonymous identity none are not supported";
      }
      {
        assertion = builtins.all (
          user: user == "*" || (userName.check user && user != "none")
        ) cfg.settings.trusted-users;
        message = "nix.settings.trusted-users accepts native usernames or *; @group selectors and the anonymous identity none are not supported";
      }
      {
        assertion = config.files."nix.conf" == text;
        message = "configure nix.conf through nix.settings instead of files.\"nix.conf\"";
      }
    ];
  };
}
