# Develop packages

Run from the checkout on Linux. Use `nix flake show` to list packages and apps,
then replace `PACKAGE` below with a target such as `lua`:

```sh
nix build .#PACKAGE
nix build .#PACKAGE-tests -o result-tests -L
```

Use the second command when a `-tests` target exists. Tests save `results.json`;
add `--rebuild` to rerun a cached test. Compiler and POSIX checks are available
as `c-abi-tests` and `ape-tests`.

Initial source and header extraction and guest tests require KVM access for Nix
builders. Cross compilation runs on Linux using the cached extracts.
`nix flake check` checks the Go executable format; run the test targets for guest
execution. Use `nix fmt` to format all Nix files.

## Add a C package

The flake exports `lib.mkPlan9Program`:

```nix
mkPlan9Program {
  name = "my-program";
  sources = [ ./main.c ];
}
```

It compiles on Linux, links with rebuilt libc, checks the executable format,
and installs `bin/my-program`. Optional arguments are `includeDirs`, `libraries`
(for rebuilt library packages), and `meta`.

APE packages use the shared [compile and link functions](../lib/ape-build.sh).
See [package definitions](../pkgs) for examples and dependencies.

Use `lib.mkGuestPackage { name = "my-program-1"; package = myProgram; }` to
archive one output for [guest installation](vm.md#install-packages).
`lib.mkGuestEnvironment { name = "tools"; packages = [ myPackage ]; }` combines
package archives and rejects conflicting command names. Include dependencies
explicitly. `package-tests` checks installation and use of the default environment.

## Build inside 9front

```sh
nix build .#hello-c-native
nix run .#smoke-test-c
```

Nix boots a temporary guest, compiles and tests C with the guest toolchain,
and returns the executable to the store. The smoke test runs it in a fresh VM.
