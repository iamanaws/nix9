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
  disabled = system false pins.one;
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
in
{
  one = system true pins.one;
  two = system true pins.two;
  inherit disabled;
  invalid = system "yes" pins.one;
  # Simulate a generation built before services were added (b9b9909).
  legacy = disabled.overrideAttrs (old: {
    name = "nix9-system-legacy";
    buildCommand = old.buildCommand + ''
      rm -r $out/services
      echo 'nix9NextSystem='$out > $out/activate
      echo -n ${quote (builtins.readFile ./services-legacy.rc)} >> $out/activate
    '';
  });
}
