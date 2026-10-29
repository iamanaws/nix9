{
  pkgs ? import <nix9>,
}:
let
  make =
    version:
    pkgs.mkSystem {
      hostName = "directory-test";
      logging.enable = true;
      directories = {
        "/usr/glenda/nix9-state" = {
          mode = if version == "one" then "0750" else "0710";
          owner = "glenda";
          group = if version == "one" then "sys" else "glenda";
        };
        "/usr/glenda/nix9-state/nested/deeper".mode = if version == "one" then "0710" else "0750";
        "/usr/glenda/nix9-preserved".mode = "0700";
        "/usr/glenda/nix9-recreated".mode = "0750";
      }
      // pkgs.lib.optionalAttrs (version == "one") {
        "/usr/glenda/nix9-only-one".mode = "0700";
      };
    };
  invalid =
    directories:
    pkgs.mkSystem {
      hostName = "invalid";
      inherit directories;
    };
in
{
  one = make "one";
  two = make "two";
  removed = pkgs.mkSystem {
    hostName = "directory-test";
    logging.enable = true;
  };
  conflict = invalid {
    "/usr/glenda/nix9-a-new" = { };
    "/usr/glenda/nix9-z-conflict/child" = { };
  };
  special = invalid { "/usr/glenda/nix9-special" = { }; };
  deniedOwner = invalid { "/usr/glenda/nix9-state".owner = "none"; };
  unknownGroup = invalid { "/usr/glenda/nix9-state".group = "nix9-missing-group"; };
  invalidPath = invalid { "relative" = { }; };
  traversal = invalid { "/usr/glenda/../escape" = { }; };
  repeatedSlash = invalid { "/usr//glenda/escape" = { }; };
  trailingSlash = invalid { "/usr/glenda/escape/" = { }; };
  storePath = invalid { "/usr/local/nix/store/invalid" = { }; };
  protectedPath = invalid { "/usr/local/nix/state" = { }; };
  protectedParent = invalid { "/usr/local" = { }; };
  namespacePath = invalid { "/n/data" = { }; };
  generatedPath = invalid { "/cfg/nix9/files/data" = { }; };
  invalidMode = invalid { "/usr/glenda/data".mode = "8888"; };
  specialMode = invalid { "/usr/glenda/data".mode = "1755"; };
  numericMode = invalid { "/usr/glenda/data".mode = 755; };
  invalidOwner = invalid { "/usr/glenda/data".owner = "*"; };
  invalidGroup = invalid { "/usr/glenda/data".group = "bad group"; };
  unknownOption = invalid { "/usr/glenda/data".recursive = true; };
  mountedPath = pkgs.mkSystem {
    hostName = "invalid";
    directories."/usr/glenda/mounted/data" = { };
    namespace.mounts.data = {
      address = "tcp!files!17020";
      mountPoint = "/usr/glenda/mounted";
    };
  };
  merged = pkgs.mkSystem {
    hostName = "merged";
    imports = [
      ({ lib, ... }: { directories."/usr/glenda/merged".mode = lib.mkDefault "0755"; })
      { directories."/usr/glenda/merged".owner = "glenda"; }
    ];
    directories."/usr/glenda/merged".mode = "0700";
  };
}
