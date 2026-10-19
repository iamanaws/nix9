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

Start with the [README quick start](../README.md#quick-start). On the host, build
the separate package set with `nix build .#native-packages -o result-native-packages`.
With the HTTP server running, install it and build in the guest:

```sh
. /usr/local/pkg/nix-2.34.8/activate
hget -o /tmp/packages.tar http://10.0.2.2:8000/result-native-packages
cd / && tar xf /tmp/packages.tar
cd /usr/local/pkg/native-packages
roots=/usr/local/nix/state/gcroots
nix-build -A fortune --out-link $roots/package
result=`{cat $roots/package}
$result/bin/fortune
```

For your own project, copy [examples/hello](../examples/hello) into the guest and
run `nix-build` in that directory. Its mkfile uses the standard build rules.
The source and recipe stay in your project.

For an interactive C development shell in that project:

```rc
nix-build shell.nix --out-link $roots/development
development=`{cat $roots/development}
$development/shell
```

Run `mk` to build and `mk clean` to remove build outputs. Exit to restore the
original namespace. `mkShell` accepts `nativeBuildInputs`,
`buildInputs` and an rc `shellHook`.

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
an environment fail the build. Keep a root for each environment you want to reuse.
The optional `files` attribute maps existing absolute file paths to text.
Activation binds the generated files in the shell's namespace. Switching away
reveals the original files.

To activate a rooted environment at login, add this line at the end of `$home/lib/profile`:

```rc
. /usr/local/pkg/native-packages/profile /usr/local/nix/state/gcroots/environment
```

Rebuild with the same `--out-link` to change the environment for future logins.
Source the profile helper again to switch the current shell.

The store persists at `/usr/local/nix/store`.
`nix-build` evaluates and builds the selected package. Its default root is
`state/gcroots/result`; use `--no-out-link` to leave no permanent root.
Roots are files containing store paths, not symlinks. Remove a root file to release
it, then run `nix-store --gc` to collect unused paths. Running programs outside a
Nix build need an explicit root. Close other store clients before collection.
Packages use [mkDerivation](../lib/mk-derivation.nix) with store-provided sources
and bootstrap tools. Recipes can use `pname`/`version`, `buildPhase` and
`installPhase`, with `checkPhase` enabled by `doCheck = true`. Each phase accepts
`pre` and `post` hooks, such as `preBuild` and `postInstall`. Directory sources
are copied to `source`; tar archives need an explicit `sourceRoot`. Override
`unpackPhase` for other formats, or use `buildCommand` for a single script.
Customize a package with `package.overrideAttrs (old: { version = "2"; })`.
Each builder gets a private namespace for its tools, headers,
and libraries. Other host files remain accessible.
`nativeBuildInputs` adds commands to rc's `path` and POSIX `PATH`.
`buildInputs` exposes `include` and `lib` in the compiler namespace.
APE dependencies use `include/ape` and `lib/ape` instead.

The package set includes `fetchurl { url = "…"; hash = "sha256-…"; }` for downloads
through 9front's `webfs`. Configure networking in the guest before fetching.
Native `lua` builds against `liblua`. Both fetch the same pinned archive and
compile with APE.
`nix-util-tests` checks fetching, isolated builds and reuse after reboot.

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
read-only 9P mount. No cache is configured by default.
With other store clients stopped, `nix-store --verify --check-contents` checks the
store and removes registrations for missing, unreferenced paths.
Under the same restriction, `nix-store --repair-path PATH` restores a path
from a configured cache. It verifies the replacement before copying it into place.
An interrupted copy requires another repair after offline recovery.
To publish natively, generate a key with `nix-store --generate-binary-cache-key NAME SECRET PUBLIC`,
then import the closure with `--store 'file:///path/to/cache?store=/usr/local/nix/store&secret-key=/path/to/SECRET'`.
Share the cache and public key. Keep the secret key private.

After an unclean shutdown, reboot, activate Nix, and run `nix-store --recover`
before opening the store. It removes stale lock markers and lets SQLite recover
its journal. Then rebuild or repair interrupted outputs and verify them.
Recovery refuses to run once a store client has opened during the current boot.
All clients must share the same canonical store path and kernel service namespace.
The [recovery test](../tests/native_recovery.py) checks rollback, rebuilding and GC.
