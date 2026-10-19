{
  pkgs ? import /usr/local/pkg/native-packages,
}:
pkgs.callPackage ./package.nix { }
