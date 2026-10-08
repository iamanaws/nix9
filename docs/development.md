# Develop packages

The flake packages cross-compile on Linux. Native Nix builds run inside Plan 9.
Run from the checkout. Use `nix flake show` to list packages and apps,
then replace `PACKAGE` below with a target such as `lua`:

```sh
nix build .#PACKAGE
nix build .#PACKAGE-tests -o result-tests -L
```

Use the second command when a `-tests` target exists. Tests save `results.json`.
Add `--rebuild` to rerun a cached test. Compiler and POSIX checks are available
as `c-abi-tests` and `ape-tests`.

Nix builders need KVM access to extract bootstrap sources and headers and run
guest tests. Cross-builds run on Linux with the cached extracts.
`nix flake check` checks the Go executable format. Run the test targets to check
execution in the guest. Use `nix fmt` to format all Nix files.

## Toolchains

Cross-builds use goken9cc's `6c` and `6l` for Plan 9 C, with GCC preprocessing
for APE. Nix and its C++ dependencies use Clang, LLD and the cc9 runtime;
`elf2aout` converts the executable format. Go examples use `GOOS=plan9`.

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
and `meta`. Pass rebuilt library packages through `libraries`.

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

## Native Nix

Start with the [README quick start](../README.md#quick-start), then run in the guest:

```sh
. /usr/local/pkg/nix-2.34.8/activate
cd /usr/local/pkg/nix-2.34.8/share/nix9
roots=/usr/local/nix/state/gcroots
nix-build -A sha1sum --out-link $roots/package
result=`{cat $roots/package}
echo -n abc | $result/bin/sha1sum
```

The store persists at `/usr/local/nix/store`. Activate the environment after login.
`nix-build` evaluates and builds the selected package. Its default root is
`state/gcroots/result`; use `--no-out-link` to leave no permanent root.
Roots are files containing store paths, not symlinks. Remove a root file to release
it, then run `nix-store --gc` to collect unused paths. Running programs outside a
Nix build need an explicit root. Close other store clients before collection.
Packages use [mkDerivation](../lib/mk-derivation.nix) with store-provided sources
and bootstrap tools. Each builder gets a private namespace for its tools, headers,
and libraries. Other host files remain accessible.

The package set includes `fetchurl { url = "…"; hash = "sha256-…"; }` for downloads
through 9front's `webfs`. Configure networking in the guest before fetching.
Native `lua` builds against `liblua`. Both fetch the same pinned archive and
compile with APE.
`nix-util-tests` checks fetching, isolated builds and reuse after reboot.

For a trusted transfer between machines using the same store path, export the
package and its dependencies, then import the file on the destination:

```rc
nix-store --export `{nix-store -qR $result} > closure.export
nix-store --import < closure.export
```

Root the imported package with `--realise --add-root` as above before running GC.
For automatic reuse, configure `substituters` with
`file:///path/to/cache?store=/usr/local/nix/store` and `trusted-public-keys` with
the cache's public signing key. `--realise` then fetches missing outputs and
dependencies and verifies their signatures and content hashes. The cache path can be a
read-only 9P mount. No cache is configured by default.
With other store clients stopped, `nix-store --repair-path PATH` restores a path
from a configured cache. It verifies the replacement before copying it into place.
An interrupted copy requires another repair after offline recovery.
To publish natively, generate a key with `nix-store --generate-binary-cache-key NAME SECRET PUBLIC`,
then import the closure with `--store 'file:///path/to/cache?store=/usr/local/nix/store&secret-key=/path/to/SECRET'`.
Share the cache and public key. Keep the secret key private.

After an unclean shutdown, reboot and keep Nix clients stopped during recovery.
Under `/usr/local/nix`, remove leftover files in `state/db/clients` and
`state/temproots`, and the `state/db/db.sqlite.p9lock` file. Preserve the database
and its rollback journal.
Remove the interrupted output's exact `.lock` file and leftover `store/tmp-*/.lock`
markers, then rebuild and verify the output. Never remove locks from a live store
or use `store/*.lock`. A valid output can also have that suffix.
The [recovery test](../tests/native_recovery.py) checks this procedure and SQLite journal rollback.
