let
  fixtures = import ./jobs.nix { };
  positive = [
    "one"
    "two"
    "disabled"
    "removed"
    "failed"
    "long"
    "files"
    "cpu"
    "reportChanged"
    "reportDisabled"
    "validRange"
    "validKeyFile"
  ];
  installations = [
    "unknownTarget"
    "unknownScheduler"
    "wrongScheduler"
    "wrongTarget"
    "forbiddenUser"
  ];
  negative = builtins.attrNames (builtins.removeAttrs fixtures (positive ++ [ "installation" ]));
  rejected = builtins.listToAttrs (
    map (name: {
      inherit name;
      value =
        !(builtins.tryEval (
          if builtins.elem name installations then
            fixtures.${name}.systems.files.drvPath
          else
            fixtures.${name}.drvPath
        )).success;
    }) negative
  );
  manifest = fixtures.installation.manifest;
in
assert builtins.all (name: builtins.isString fixtures.${name}.drvPath) positive;
assert builtins.all (x: x) (builtins.attrValues rejected);
assert manifest.jobs.report.scheduler == "files";
assert manifest.jobs.report.target == "cpu";
assert builtins.any (
  d: d.kind == "job" && d.consumer == "files" && d.provider == "cpu" && d.phase == "run"
) manifest.dependencies;
{
  status = "passed";
  inherit positive rejected;
}
