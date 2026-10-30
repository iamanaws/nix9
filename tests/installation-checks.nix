let
  fixtures = import ./installation.nix { };
  valid = fixtures.valid;
  renamed = fixtures.renamed;
  sharing = import ./sharing.nix { };
  sharingSystems = [
    "files"
    "cpu"
    "terminal"
    "readOnly"
    "disabled"
    "moved"
    "optional"
    "unavailable"
    "empty"
  ];
  positive = [
    "valid"
    "deployment"
    "retiringCpu"
    "renamed"
    "movedPort"
    "optional"
    "noConsumerMounts"
    "minimal"
    "mutualMounts"
  ];
  invalid = builtins.attrNames (builtins.removeAttrs fixtures positive);
  # Request only one system: invalid declarations elsewhere must still fail.
  rejected = builtins.listToAttrs (
    map (name: {
      inherit name;
      value = !(builtins.tryEval fixtures.${name}.systems.files.drvPath).success;
    }) invalid
  );
in
assert builtins.all (value: value) (builtins.attrValues rejected);
assert builtins.all (name: builtins.isString sharing.${name}.drvPath) sharingSystems;
assert builtins.isString valid.build.drvPath;
assert valid.manifest.version == 1;
assert
  builtins.attrNames valid.systems == [
    "cpu"
    "files"
    "terminal"
  ];
assert
  valid.manifest.machines.files.roles == [
    "auth"
    "file"
  ];
assert valid.manifest.machines.cpu.roles == [ "cpu" ];
assert valid.manifest.machines.terminal.roles == [ ];
assert
  valid.manifest.machines.cpu.deployment == {
    remote = true;
    host = "10.0.2.101";
    user = null;
    keyPattern = "dom=nix9.share";
    timeout = 300;
  };
assert !valid.manifest.machines.terminal.deployment.remote;
assert fixtures.deployment.manifest.machines.cpu.deployment.host == "cpu-admin";
assert fixtures.deployment.manifest.machines.cpu.deployment.user == "glenda";
assert fixtures.retiringCpu.manifest.machines.cpu.deployment.remote;
assert fixtures.retiringCpu.manifest.machines.cpu.roles == [ ];
assert valid.manifest.machines.cpu.mounts.projects.address == "tcp!files!17020";
assert valid.manifest.machines.cpu.mounts.projects.keyPattern == "dom=nix9.share";
assert renamed.manifest.machines.files.machineId == "file-id";
assert renamed.discovery.hosts.storage.auth == "storage";
assert renamed.manifest.machines.cpu.mounts.projects.address == "tcp!storage!17020";
assert fixtures.movedPort.manifest.machines.cpu.mounts.projects.address == "tcp!files!17025";
assert builtins.any (
  dependency: dependency.kind == "mount" && dependency.consumer == "terminal" && !dependency.required
) fixtures.optional.manifest.dependencies;
assert builtins.all (dependency: dependency.phase == "session") valid.manifest.dependencies;
assert builtins.any (
  dependency:
  dependency.kind == "authentication" && dependency.consumer == "terminal" && !dependency.required
) fixtures.optional.manifest.dependencies;
assert builtins.all (
  dependency: dependency.consumer != "terminal"
) fixtures.noConsumerMounts.manifest.dependencies;
assert fixtures.minimal.manifest.dependencies == [ ];
assert fixtures.mutualMounts.manifest.machines.one.mounts.data.address == "tcp!two!17020";
assert fixtures.mutualMounts.manifest.machines.two.mounts.data.address == "tcp!one!17020";
{
  status = "passed";
  inherit positive rejected;
  inherit sharingSystems;
  checks = [
    "generated-discovery"
    "derived-roles"
    "provider-endpoints"
    "stable-identities"
    "optional-dependencies"
    "whole-inventory-validation"
  ];
}
