{
  pkgs ? import <nix9>,
}:
pkgs.mkInstallation ./configuration.nix
