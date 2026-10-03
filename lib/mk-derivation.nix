{ tools }:
attrs@{ name, buildCommand, ... }:
derivation (
  {
    inherit name tools;
    system = "x86_64-plan9";
    builder = "${tools}/bin/rc";
    args = [
      "-m"
      "${tools}/rcmain"
      "-e"
      "-c"
      buildCommand
    ];
  }
  // builtins.removeAttrs attrs [ "buildCommand" ]
)
