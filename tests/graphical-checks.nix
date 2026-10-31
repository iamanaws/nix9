let
  fixtures = import ./graphical.nix { };
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) fixtures.invalid;
in
assert builtins.all (value: value) (builtins.attrValues rejected);
assert builtins.isString fixtures.first.build.drvPath;
assert builtins.isString fixtures.second.build.drvPath;
assert builtins.isString fixtures.disabled.build.drvPath;
assert builtins.isString (import <nix9/examples/workstation> { }).build.drvPath;
{
  status = "passed";
  inherit rejected;
}
