let
  fixtures = import ./netroot.nix { };
  rejected = builtins.mapAttrs (
    _: value: !(builtins.tryEval value.systems.auth.drvPath).success
  ) fixtures.invalid;
  inherit (fixtures.first) manifest;
in
assert builtins.all (value: value) (builtins.attrValues rejected);
assert builtins.isString fixtures.first.build.drvPath;
assert builtins.isString fixtures.first.boot.build.drvPath;
assert builtins.isString fixtures.first.boot.batch.drvPath;
assert builtins.isString fixtures.first.roots.stable.drvPath;
assert fixtures.first.roots.stable.outPath == fixtures.second.roots.stable.outPath;
assert
  fixtures.first.manifest.machines.build.boot.rootDirectory
  != fixtures.second.manifest.machines.build.boot.rootDirectory;
assert
  fixtures.first.manifest.machines.batch.boot.rootDirectory
  == fixtures.second.manifest.machines.batch.boot.rootDirectory;
assert
  fixtures.first.manifest.machines.build.boot.stateDirectory
  == fixtures.second.manifest.machines.build.boot.stateDirectory;
assert manifest.roots.stable.directory == manifest.machines.build.boot.rootDirectory;
assert manifest.roots.stable.bundle == toString fixtures.first.roots.stable;
assert builtins.isString (import <nix9/examples/netroot> { }).build.drvPath;
assert manifest.machines.build.boot.address == "tcp!10.0.2.101!564";
assert manifest.machines.build.boot.auth == "10.0.2.100";
assert manifest.machines.build.boot.stateDirectory == "/machines/build";
assert manifest.machines.batch.boot.stateDirectory == "/machines/batch";
assert manifest.machines.auth.boot == null;
assert fixtures.renamed.manifest.machines.build.boot.stateDirectory == "/machines/builder-id";
assert fixtures.renamed.manifest.machines.build.hostName == "worker";
assert builtins.any (
  dependency:
  dependency.consumer == "build"
  && dependency.provider == "files"
  && dependency.kind == "root"
  && dependency.phase == "boot"
) manifest.dependencies;
assert builtins.any (
  dependency:
  dependency.consumer == "build"
  && dependency.provider == "auth"
  && dependency.kind == "authentication"
  && dependency.phase == "boot"
) manifest.dependencies;
{
  status = "passed";
  inherit rejected;
}
