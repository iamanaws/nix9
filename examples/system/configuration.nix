let
  pkgs = import <nix9>;
in
pkgs.mkSystem {
  hostName = "nix9";
  packages = [ pkgs.fortune ];
  files."motd" = "Welcome to nix9.\n";
  # webfs.certificatePins."example.org" = [ "64 hexadecimal SHA-256 digits" ];
}
