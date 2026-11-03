let
  fixtures = import ./store-service.nix { };
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) fixtures.invalid;
in
assert builtins.all (name: builtins.isString fixtures.${name}.drvPath) [
  "initial"
  "moved"
  "disabled"
  "provisioned"
];
assert builtins.all (value: value) (builtins.attrValues rejected);
{
  status = "passed";
  inherit rejected;
}
