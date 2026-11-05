let
  hashes = builtins.fromJSON (builtins.readFile ./input-hashes.json);
  definitions = import ./pkgs/packages.nix {
    sources = builtins.mapAttrs (name: _: ./sources + "/${name}") (builtins.readDir ./sources);
  };
in
{
  tools = builtins.path {
    path = ./tools;
    sha256 = hashes.tools;
  };
  packages = builtins.mapAttrs (
    name: definition:
    definition
    // {
      args = builtins.mapAttrs (
        argument: value:
        if hashes.packages.${name} ? ${argument} then
          builtins.path {
            path = value;
            sha256 = hashes.packages.${name}.${argument};
          }
        else
          value
      ) definition.args;
    }
  ) definitions;
}
