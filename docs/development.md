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

Follow the [VM instructions](vm.md#install-packages), replacing `guest-environment`
with `guest-development`.
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

Start with the [README quick start](../README.md#quick-start). The bootstrap archive
includes the package set and a signed cache for its development tools. In the guest:

```sh
. /usr/local/pkg/nix9/activate
cd $nix9/packages
roots=/usr/local/nix/state/gcroots
nix-build -A fortune --out-link $roots/package
result=`{cat $roots/package}
$result/bin/fortune
```

For your own project, copy `$nix9/hello` to a writable directory and
run `nix-build` there. Its mkfile uses the standard build rules.
The source and recipe stay in your project.

The archive also includes a [ramfs example](../examples/ramfs). It mounts a memory filesystem in a
private namespace, writes a file and unmounts it:

```rc
nix-build $nix9/ramfs --out-link $roots/ramfs
rc $nix9/ramfs/run.rc `{cat $roots/ramfs}
```
`pkgs.callPackage ./package.nix { }` supplies recipe dependencies; explicit arguments override them.

For an interactive C development shell in that project:

```rc
nix-shell
```

Run `mk` to build and `mk clean` to remove build outputs. Exit to restore the
original namespace, or use `nix-shell --run 'mk'` for one command.
The shell keeps its dependencies rooted until it exits. `mkShell` accepts
`nativeBuildInputs`, `buildInputs` and an rc `shellHook`. Use `inputsFrom` to reuse
a derivation's build dependencies and shell hook.

[environment.nix](../examples/environment.nix) combines packages and configuration with `buildEnv`.
Copy it into the guest, then build and activate it:

```rc
nix-build environment.nix --out-link $roots/environment
environment=`{cat $roots/environment}
touch /tmp/nix9.lua
. $environment/activate
lua /tmp/nix9.lua
```

Source another environment's `activate` file to switch. Command collisions within
an environment fail the build.
The optional `files` attribute maps existing absolute file paths to text.
Activation binds the generated files in the shell's namespace. Switching away
reveals the original files.

To keep generations and roll back:

```rc
profile=$nix9/bin/nix-profile
$profile $roots/environment set $environment
$profile $roots/environment list
```

`set` retains the previous environment. `rollback` selects the preceding generation.
`delete NUMBER` releases an inactive generation for GC.
Selecting a retained environment reuses its generation.
Add these lines at the end of `$home/lib/profile` to activate the selected environment at login:

```rc
. /usr/local/pkg/nix9/activate
. $nix9/packages/profile /usr/local/nix/state/gcroots/environment
```

Source the second line again after `set` or `rollback` to switch the current shell.
Build updates with a separate `--out-link`, then use `set` to select them.

To update from published recipes, run `nix build .#native-package-source` on Linux
and serve its `packages.tar.gz`. Copy the generated `update.nix` into the guest
and change its URL. It pins the archive's unpacked hash; edit `paths` to select packages.
With webfs mounted, run:

```rc
nix-build update.nix --out-link $roots/update &&
  nix-profile $roots/environment set `{cat $roots/update}
. $nix9/packages/profile $roots/environment
```

Use `rollback` to return to the previous environment. Updating recipes keeps the
installed Nix commands. Fetched recipes can be reused offline until GC removes them.

To retain complete releases of Nix and its package set:

```rc
nix-build /usr/local/pkg/nix9/release.nix --out-link $roots/release
nix-profile $roots/nix9 set `{cat $roots/release}
. /usr/local/pkg/nix9/activate
```

After installing a new bootstrap archive, repeat these commands to upgrade.
Installation leaves the selected release unchanged.
Use `nix-profile $roots/nix9 rollback`, then source the activation file again to
switch back. Release generations retain their files through GC, just like environments.

The store persists at `/usr/local/nix/store`.
`nix-build` evaluates and builds the selected package. Its default root is
`state/gcroots/result`; use `--no-out-link` to leave no permanent root.
`nix-build --check` compares a rebuild with the registered output without replacing it.
Roots are files containing store paths, not symlinks. Remove a root file to release
it, then run `nix-store --gc` to collect unused paths. Running programs outside a
Nix build need an explicit root. Close other store clients before collection.
Packages use `stdenv.mkDerivation` with native rc, `6a`, `6c`, `6l`, libc and mk.
`mkDerivation` remains an alias. With a mkfile, the default phases
run `mk` and `mk install BIN=$out/bin`. Set `makefile` for another filename and use
the list attributes `makeFlags`, `buildFlags` and `installFlags` for arguments.
Recipes can use `pname`/`version` and override `buildPhase` or `installPhase`.
Enable `checkPhase` with `doCheck = true`.
Each phase accepts `pre` and `post` hooks, such as `preBuild` and `postInstall`.
Use `patches = [ ./fix.patch ];` for unified diffs. `patchFlags` defaults to `[ "-p1" ]`.
`phases` selects their order and can include custom steps such as `generatePhase`.
Directory sources are copied to `source`; tar archives need an explicit
`sourceRoot`. Override
`unpackPhase` for other formats, or use `buildCommand` for a single script.
Use `package.override { dependency = replacement; }` to change `callPackage` arguments,
or `package.overrideAttrs (old: { version = "2"; })` to change derivation attributes.
`meta` holds package metadata; `passthru` exposes extra package attributes.
Neither enters the build environment.
Each builder gets a private namespace for its tools, headers,
and libraries. Normal builds use the rebuilt compiler and declared libraries;
seed compilers and libraries are bound during bootstrapping. Other host files remain accessible.
`nativeBuildInputs` adds commands to rc's `path` and POSIX `PATH`.
`buildInputs` exposes `include` and `lib` in the compiler namespace.
Use `propagatedNativeBuildInputs` or `propagatedBuildInputs` to pass those
dependencies on to consumers.
APE dependencies use `include/ape` and `lib/ape` instead.

The package set includes `fetchurl { url = "…"; hash = "sha256-…"; }` for downloads
through 9front's `webfs`. Configure networking in the guest before fetching.
`builtins.fetchurl { url = "…"; sha256 = "sha256-…"; }` fetches files during
evaluation. Mount webfs first with `webfs -m /mnt/web -T 60000`.
Use `builtins.fetchTarball` for archives; its `sha256` is the unpacked tree's NAR
hash. It strips a single enclosing directory. Pinned files and trees can be reused offline.
Native `lua` builds against `liblua`. Both fetch the same pinned archive and
compile with APE.
Use `nix-native-tests` for native packages and shells, `nix-core-tests` for libraries
and commands, or `nix-store-tests` for transfers and caches. Store tests reuse the
native suite's exported closure. `nix-util-tests` runs all three.

For a trusted transfer between machines using the same store path, export the
package and its dependencies, then import the file on the destination:

```rc
nix-store --export `{nix-store -qR $result} > /tmp/closure.export
nix-store --import < /tmp/closure.export
```

Root the imported package with `nix-store --realise --add-root $roots/package $result`
before running GC.
For automatic reuse, configure `substituters` with
`file:///path/to/cache?store=/usr/local/nix/store` and `trusted-public-keys` with
the cache's public signing key. `--realise` then fetches missing outputs and
dependencies and verifies their signatures and content hashes. The cache path can be a
read-only 9P mount. HTTP(S) caches use the same settings with a URL such as
`https://cache.example?store=/usr/local/nix/store`. First mount webfs with
`webfs -m /mnt/web -T 60000`. Network caches are read-only; webfs controls the
transport and does not validate server certificates. The bootstrap archive configures
its bundled file cache.
With other store clients stopped, `nix-store --verify --check-contents` checks the
store and removes registrations for missing, unreferenced paths.
Under the same restriction, `nix-store --repair-path PATH` restores a path
from a configured cache or rebuilds an available derivation. `nix-build --repair`
checks and repairs a package's outputs and dependencies.
An interrupted replacement requires another repair after offline recovery.
To publish natively, generate a key with `nix-store --generate-binary-cache-key NAME SECRET PUBLIC`,
then import the closure with `--store 'file:///path/to/cache?store=/usr/local/nix/store&secret-key=/path/to/SECRET'`.
Share the cache and public key. Keep the secret key private.

After an unclean shutdown, reboot, activate Nix, and run `nix-store --recover`
before opening the store. It removes stale lock markers and lets SQLite recover
its journal. Then rebuild or repair interrupted outputs and verify them.
Recovery refuses to run once a store client has opened during the current boot.
All clients must share the same canonical store path and kernel service namespace.
The [recovery test](../tests/native_recovery.py) checks rollback, rebuilding and GC.
