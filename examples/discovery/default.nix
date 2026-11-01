{
  pkgs ? import <nix9>,
}:
pkgs.mkInstallation { imports = [ ./configuration.nix ]; }
