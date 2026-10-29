{
  machineId ? null,
}:
let
  pkgs = import <nix9>;
  system =
    name:
    pkgs.mkSystem {
      inherit machineId;
      hostName = name;
      files.version = name + "\n";
    };
in
{
  one = system "machine-one";
  two = system "machine-two";
  wrong = (system "wrong-machine").overrideAttrs (old: {
    buildCommand = old.buildCommand + "echo other-machine > $out/machine-id\n";
  });
}
