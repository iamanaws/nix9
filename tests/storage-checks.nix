let
  fixtures = import ./storage.nix { };
  manifest = fixtures.initial.manifest;
  positive = [
    "auth"
    "files"
    "build"
    "batch"
    "terminal"
    "noDumps"
  ];
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) fixtures.invalid;
in
assert builtins.all (name: builtins.isString fixtures.${name}.drvPath) positive;
assert builtins.all (value: value) (builtins.attrValues rejected);
assert manifest.machines.files.roles == [ "file" ];
assert manifest.machines.files.endpoints.cwfs.address == "tcp!files!564";
assert manifest.machines.build.mounts.work.transport == "tcp";
assert manifest.machines.build.mounts.work.attach == "main";
assert manifest.machines.terminal.mounts.history.attach == "dump";
assert manifest.machines.terminal.mounts.history.fileSystem == "dump";
{
  status = "passed";
  inherit positive rejected;
}
