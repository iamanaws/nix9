let
  fixtures = import ./bindings.nix { };
  positive = [
    "one"
    "two"
    "removed"
    "unavailable"
    "optional"
    "chain"
    "merged"
  ];
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) (
    builtins.removeAttrs fixtures positive
  );
in
assert builtins.all (name: builtins.isString fixtures.${name}.drvPath) positive;
assert builtins.all (value: value) (builtins.attrValues rejected);
{
  status = "passed";
  inherit positive rejected;
}
