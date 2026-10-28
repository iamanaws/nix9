let
  pkgs = import <nix9>;
in
pkgs.mkSystem {
  hostName = "nix9";
  networking.enable = true;
  services.webfs.enable = true;
  # services.timesync.enable = true; # Hardware RTC in UTC; see docs for NTP.
  packages = [ pkgs.fortune ];
  files."motd" = "Welcome to nix9.\n";
  # webfs.certificatePins."example.org" = [ "64 hexadecimal SHA-256 digits" ];
}
