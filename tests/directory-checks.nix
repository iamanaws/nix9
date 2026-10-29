let
  fixtures = import ./directories.nix { };
  positive = [
    "one"
    "two"
    "removed"
    "conflict"
    "special"
    "deniedOwner"
    "unknownGroup"
    "merged"
  ];
  invalid = builtins.attrNames (builtins.removeAttrs fixtures positive);
  rejected = builtins.listToAttrs (
    map (name: {
      inherit name;
      value = !(builtins.tryEval fixtures.${name}.drvPath).success;
    }) invalid
  );
in
assert builtins.all (name: builtins.isString fixtures.${name}.drvPath) positive;
assert builtins.all (value: value) (builtins.attrValues rejected);
{
  status = "passed";
  inherit positive rejected;
}
