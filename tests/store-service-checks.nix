let
  pkgs = import <nix9>;
  evaluate =
    configuration:
    (import <nix9/system/eval.nix> {
      inherit pkgs;
      inherit (pkgs) lib;
    } configuration).config;
  merged = evaluate {
    hostName = "settings";
    imports = [
      {
        nix.settings = {
          allowed-users = [ "alice" ];
          substituters = [ "https://cache.example" ];
        };
      }
      ({ lib, ... }: {
        nix.settings = {
          allowed-users = lib.mkForce [ "bob" ];
          substituters = lib.mkAfter [ "file:///cache" ];
          keep-failed = true;
          cores = 2;
          max-jobs = "auto";
          system-features = [ "batch" ];
          builders = null;
        };
      })
    ];
  };
  fixtures = import ./store-service.nix { };
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) fixtures.invalid;
in
assert builtins.all (name: builtins.isString fixtures.${name}.drvPath) [
  "initial"
  "live"
  "invalidLive"
  "moved"
  "disabled"
  "provisioned"
  "wildcard"
  "empty"
  "trusted"
];
assert merged.nix.settings.allowed-users == [ "bob" ];
assert
  merged.files."nix.conf"
  == "allowed-users = bob\ncores = 2\nkeep-failed = true\nmax-jobs = auto\nsubstituters = https://cache.example file:///cache\nsystem-features = batch\ntrusted-users = \n";
assert builtins.all (value: value) (builtins.attrValues rejected);
{
  status = "passed";
  inherit rejected;
}
