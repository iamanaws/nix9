let
  fixtures = import ./users.nix { };
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) fixtures.invalid;
in
assert builtins.isString fixtures.shared.drvPath;
assert builtins.isString fixtures.membership.drvPath;
assert builtins.isString fixtures.initial.build.drvPath;
assert builtins.all (value: value) (builtins.attrValues rejected);
{
  status = "passed";
  inherit rejected;
}
