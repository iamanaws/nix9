let
  fixtures = import ./builders.nix { };
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) fixtures.invalid;
  pkgs = import <nix9>;
  evaluate =
    configuration:
    (import <nix9/system/eval.nix> {
      inherit pkgs;
      inherit (pkgs) lib;
    } configuration).config;
  machine = {
    hostName = "build";
    user = "alice";
    keyPattern = "dom=example";
    mandatoryFeatures = [ "batch" ];
  };
  active = evaluate {
    hostName = "terminal";
    nix = {
      distributedBuilds = true;
      buildMachines = [ machine ];
    };
  };
  inactive = evaluate {
    hostName = "terminal";
    nix.buildMachines = [ machine ];
  };
  timed = evaluate {
    hostName = "terminal";
    nix = {
      distributedBuilds = true;
      buildMachines = [ (machine // { connectTimeout = 7; }) ];
    };
  };
  unlimited = evaluate {
    hostName = "terminal";
    nix = {
      distributedBuilds = true;
      buildMachines = [
        {
          hostName = "build";
          connectTimeout = 0;
        }
      ];
    };
  };
  explicit = evaluate {
    hostName = "terminal";
    nix.settings.builders = "cpu://build";
  };
  forced = evaluate (
    { lib, ... }: {
      hostName = "terminal";
      nix.settings = lib.mkForce { cores = 2; };
    }
  );
  builders = fixtures.initial.manifest.machines.terminal.builders;
in
assert
  active.nix.settings.builders
  == "cpu://alice@build?key-pattern=dom%3Dexample x86_64-plan9 - 1 1 batch batch";
assert inactive.nix.settings.builders == "";
assert
  timed.nix.settings.builders
  == "cpu://alice@build?key-pattern=dom%3Dexample&connect-timeout=7 x86_64-plan9 - 1 1 batch batch";
assert unlimited.nix.settings.builders == "cpu://build?connect-timeout=0 x86_64-plan9 - 1 1 - -";
assert explicit.nix.settings.builders == "cpu://build";
assert builtins.elem pkgs.rcpu explicit.packages;
assert forced.packages == [ ];
assert builtins.all (value: value) (builtins.attrValues rejected);
assert builtins.isString fixtures.initial.build.drvPath;
assert builtins.match ".*builder build: build.*" fixtures.initial.overview != null;
assert builtins.match ".*builder build: compile.*" fixtures.renamed.overview != null;
assert builtins.isString fixtures.second.build.drvPath;
assert builtins.isString fixtures.standalone.drvPath;
assert builtins.isString fixtures.extended.build.drvPath;
assert builtins.isString fixtures.stopped.build.drvPath;
assert builtins.isString fixtures.singular.drvPath;
assert builtins.length fixtures.extended.manifest.machines.terminal.buildMachines == 2;
assert builtins.isString (import <nix9/examples/builders> { }).build.drvPath;
assert builders.build.hostName == "build";
assert builders.build.keyPattern == "dom=nix9.builders";
assert builders.build.maxJobs == 1;
assert builders.build.connectTimeout == 30;
assert fixtures.renamed.manifest.machines.terminal.builders.build.hostName == "compile";
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
