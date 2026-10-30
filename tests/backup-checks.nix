let
  fixtures = import ./backups.nix { };
  manifest = fixtures.initial.manifest;
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) fixtures.invalid;
in
assert builtins.all (value: value) (builtins.attrValues rejected);
assert builtins.isString fixtures.initial.build.drvPath;
assert manifest.jobs.projects-backup.scheduler == "auth";
assert manifest.jobs.projects-backup.target == "build";
assert manifest.machines.build.mounts.history.attach == "dump";
assert manifest.machines.build.mounts.archives.provider == "backup";
assert manifest.machines.build.mounts.archives.transport == "tls";
assert !manifest.machines.backup.endpoints.exports.archives.readOnly;
assert !manifest.machines.build.mounts.archives.required;
{
  status = "passed";
  inherit rejected;
}
