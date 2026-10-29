{ lib, pkgs }:
configuration:
lib.evalModules {
  class = "nix9";
  specialArgs = { inherit pkgs; };
  modules = [
    ./options.nix
    configuration
  ];
}
