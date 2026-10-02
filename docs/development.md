# Develop packages

Packages cross-compile on Linux; package builds do not run a compiler in a VM.
Run from the checkout. Use `nix flake show` to list packages and apps,
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

Install `guest-development` using the [VM instructions](vm.md#install-packages).
In the guest, activate it and compile native Plan 9 C:

```sh
. /usr/local/env/development/activate
6c -o main.6 main.c
6l -o main main.6
./main
```

Use `pcc -o program source.c` for POSIX C through APE. The wrappers use the guest's
tools with installed headers and rebuilt runtimes. `pcc` sets up a private
namespace for APE's standard paths. `guest-development-tests` verifies builds
with the image's headers and libraries hidden.

Native Nix builds the [C example](../pkgs/hello-c-cross/native.nix) with source
and `native-tools` imported into its store. The toolchain bundles the image's
compiler and headers with rebuilt libc. `nix-util-tests` builds and runs the
program with the image's compiler, headers and libraries hidden.
