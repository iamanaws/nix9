{ pkgs, packages }:
let
  baseCallPackage = pkgs.newScope packages;
  callPackages = pkgs.lib.callPackagesWith (packages // fixtures // { inherit pkgs vmTest; });
  vmTest = baseCallPackage ./vm-test.nix { };
  fixtures = pkgs.lib.callPackagesWith packages ./fixtures.nix {
    inherit pkgs;
    callPackage = baseCallPackage;
  };
  tests = pkgs.lib.mergeAttrsList (
    map (file: callPackages file { }) [
      ./cross.nix
      (
        {
          pkgs,
          nativePackageSet,
          testSupport,
          ...
        }:
        {
          installation-tests = import ./installation-host.nix { inherit pkgs nativePackageSet testSupport; };
          directory-tests = import ./directory-host.nix { inherit pkgs nativePackageSet testSupport; };
          job-tests = import ./job-host.nix { inherit pkgs nativePackageSet testSupport; };
          binding-tests = import ./binding-host.nix { inherit pkgs nativePackageSet testSupport; };
          network-tests = import ./network-host.nix { inherit pkgs nativePackageSet testSupport; };
        }
      )
      ./native.nix
      ./nix.nix
    ]
  );
  inherit (packages) hello;
in
{
  packages = tests // {
    c-abi-cross = fixtures.abiCross;
    ape-cross = fixtures.apeCross;
  };
  checks.hello-format =
    pkgs.runCommand "hello-plan9-format"
      {
        nativeBuildInputs = [ pkgs.go ];
      }
      ''
        export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache" GOPROXY=off GOTOOLCHAIN=local
        go run ${./format.go} ${hello}/bin/hello
        touch "$out"
      '';
  checks.installation = tests.installation-tests;
  checks.directories = tests.directory-tests;
  checks.jobs = tests.job-tests;
  checks.bindings = tests.binding-tests;
  checks.networking = tests.network-tests;
}
