{ lib }:
let
  inherit (import ./types.nix { inherit lib; }) publicKeyPattern userName;
  feature = lib.types.strMatching "[a-zA-Z0-9_+.-]+";
in
{
  user = lib.mkOption {
    type = lib.types.nullOr userName;
    default = null;
    description = "CPU login user; null uses the caller's native user.";
  };
  keyPattern = lib.mkOption {
    type = publicKeyPattern;
    default = "";
    description = "Public attributes selecting the client's factotum key.";
  };
  maxJobs = lib.mkOption {
    type = lib.types.ints.positive;
    default = 1;
    description = "Concurrent build slots on this builder, counted on the client machine.";
  };
  speedFactor = lib.mkOption {
    type = lib.types.ints.positive;
    default = 1;
    description = "Relative preference when choosing between available builders.";
  };
  systems = lib.mkOption {
    type = lib.types.nonEmptyListOf feature;
    default = [ "x86_64-plan9" ];
    description = "Nix platforms supported by the builder.";
  };
  supportedFeatures = lib.mkOption {
    type = lib.types.listOf feature;
    default = [ ];
    description = "Additional system features supported by the builder.";
  };
  mandatoryFeatures = lib.mkOption {
    type = lib.types.listOf feature;
    default = [ ];
    description = "Features a derivation must request to use this builder.";
  };
}
