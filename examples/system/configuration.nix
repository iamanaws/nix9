let
  pkgs = import <nix9>;
in
pkgs.mkSystem {
  hostName = "nix9";
  networking.enable = true;
  services.webfs.enable = true;
  # CPU servers: services.listen = { enable = true; tcp."17010" = "cat /cfg/nix9/files/motd"; };
  # services.timesync.enable = true; # Hardware RTC in UTC; see docs for NTP.
  # logging.enable = true; # Preserve native logs and record generation events.
  packages = [ pkgs.fortune ];
  files."motd" = "Welcome to nix9.\n";
  # webfs.certificatePins."example.org" = [ "64 hexadecimal SHA-256 digits" ];
}
