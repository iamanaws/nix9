let
  pkgs = import <nix9>;
  pins = import ./service-pins.nix;
  system =
    enable: pin:
    pkgs.mkSystem {
      hostName = "nix9-services";
      networking.enable = true;
      services.webfs.enable = enable;
      webfs.certificatePins."10.0.2.2" = [ pin ];
    };
in
{
  one = system true pins.one;
  two = system true pins.two;
  disabled = system false pins.one;
  invalid = system "yes" pins.one;
}
