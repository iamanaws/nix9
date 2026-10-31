let
  fixtures = import ./builders.nix { };
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) fixtures.invalid;
  builders = fixtures.initial.manifest.machines.terminal.builders;
in
assert builtins.all (value: value) (builtins.attrValues rejected);
assert builtins.isString fixtures.initial.build.drvPath;
assert builtins.isString fixtures.second.build.drvPath;
assert builtins.isString fixtures.standalone.drvPath;
assert builtins.isString (import <nix9/examples/builders> { }).build.drvPath;
assert builders.build.host == "build";
assert builders.build.keyPattern == "dom=nix9.builders";
assert builders.build.maxJobs == 1;
assert fixtures.renamed.manifest.machines.terminal.builders.build.host == "compile";
assert fixtures.second.manifest.machines.terminal.builders.batch.maxJobs == 1;
assert builtins.any (
  dep:
  dep.kind == "builder"
  && dep.consumer == "terminal"
  && dep.provider == "build"
  && dep.phase == "build"
) fixtures.initial.manifest.dependencies;
{
  status = "passed";
  inherit rejected;
}
