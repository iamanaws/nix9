# Develop packages

Use [native Nix](native.md) for everyday builds and environments. This guide
covers toolchains and package recipes; [tests](validation.md) has validation
commands.

## Toolchains

Cross-builds run on Linux without KVM. Enter `nix develop .#cross`, then run
`mk` in `examples/hello` to produce Plan 9's `6.out`. The shell puts its sysroot
and adapted mkfiles in a temporary directory.

| Target | Tools |
| --- | --- |
| Plan 9 C | Plan9port rc and mk; goken9cc 6c and 6l. |
| APE POSIX C | GCC preprocessing, pcc, libap and libbsd. |
| Nix and C++ libraries | Clang, LLD and the cc9 runtime; elf2aout converts executables. |
| Cross-built Go | Go with `GOOS=plan9`. |

Nix commands and digest implementations compile with `-O2`. Installed Nix
commands omit symbol tables; `nix build .#nix-util` retains ELF files for debugging.
For tools that compile inside 9front without Nix, use the
[guest development archive](vm.md#package-archives).

## C recipes

Cross and native package sets provide `callPackage`, `stdenv` and `mkShell`.
`callPackage ./package.nix { }` supplies dependencies; explicit arguments
override them. See [mpc](../pkgs/mpc/default.nix) for a shared recipe.

Use `stdenv.mkDerivation` for a package. `mkDerivation` is also an alias.
Builders use rc, mk, the rebuilt compiler and declared libraries in a private
namespace. Seed tools are used during bootstrapping. Other host files remain
accessible.

| Attribute | Behavior |
| --- | --- |
| `src` | Directory sources copy to `source`. Tar archives require `sourceRoot`; override `unpackPhase` for other formats. |
| `pname`, `version` | Set the package name and version. |
| `nativeBuildInputs` | Add commands to rc's `path` and POSIX `PATH`. Cross recipes use `buildPackages` for build tools. |
| `buildInputs` | Expose `include` and `lib` in the compiler namespace. APE uses `include/ape` and `lib/ape`. |
| `propagatedNativeBuildInputs`, `propagatedBuildInputs` | Pass dependencies to consumers. |
| `makefile` | Select an alternative to the default mkfile. |
| `makeFlags`, `buildFlags`, `installFlags` | Lists of command arguments. Defaults run `mk` and `mk install BIN=$out/bin`. |
| `patches`, `patchFlags` | Apply unified diffs, using `[ "-p1" ]` by default. |
| `doCheck` | Enable `checkPhase` when true. |
| `phases` | Select phase order, including custom phases. Override `buildPhase` or `installPhase`, or use `buildCommand` for one script. |
| `preBuild`, `postInstall`, etc. | Run hooks before or after a phase. |
| `meta`, `passthru` | Package metadata and extra attributes; neither enters the build environment. |

Use `package.override { dependency = replacement; }` for `callPackage` arguments,
or `package.overrideAttrs (old: { version = "2"; })` for derivation attributes.
[Source fetchers](transport.md#source-fetches) provide pinned downloads.

For a simple cross-built program, the flake exports `lib.mkPlan9Program`:

```nix
mkPlan9Program {
  name = "my-program";
  sources = [ ./main.c ];
}
```

It compiles, links with libc and installs `bin/my-program`. Optional arguments
are `includeDirs`, `libraries` and `meta`; pass rebuilt libraries explicitly.

`lib.mkGuestPackage { name = "my-program-1"; package = myProgram; }` archives
an output. `lib.mkGuestEnvironment { name = "tools"; packages = [ myPackage ]; }`
combines archives and rejects command collisions. Include dependencies explicitly,
then follow [archive installation](vm.md#package-archives).

## Development shells

Copy `$nix9/hello` into a writable project directory and run `nix-shell`.
Inside, use `mk` and `mk clean`. Exiting restores the original namespace.
`nix-shell default.nix --run 'mk'` runs one command without an interactive shell.

`nix-shell default.nix` also enters a package's build environment without
building it. Use `--pure` to clear inherited variables and `--keep NAME` to retain
one. Dependencies remain rooted until the shell exits.

`mkShell` accepts `nativeBuildInputs`, `buildInputs` and an rc `shellHook`.
Use `inputsFrom` to reuse derivations' dependencies and shell hooks.

## Native Go

The optional bootstrap includes Go 1.26.7 sources and a cross-built seed compiler.
Build it on Linux:

```sh
nix build .#native-go-bootstrap -o result-native-go-bootstrap
```

Follow the [quick start](../README.md#quick-start), substituting this archive for
`native-bootstrap`. If a complete release is selected, also follow the
[release upgrade](native.md#complete-releases) steps. Use a
[4 GiB VM](vm.md#persistent-disks) for native Go builds and tests. In the guest:

```sh
. /usr/local/pkg/nix9/activate
roots=/usr/local/nix/state/gcroots
nix-build $nix9/packages -A go --out-link $roots/go
go=`{cat $roots/go}^/bin/go
$go version
```

The toolchain rebuilds with upstream `make.rc` and has no runtime reference to
the seed. Source and seed archives use fixed-output hashes. Build caches stay in
the build directory; automatic toolchain downloads, module proxies and
checksum-service lookups are disabled.

For commands in a project with `go.mod`:

```nix
let
  pkgs = import <nix9>;
in
pkgs.buildGoModule {
  pname = "my-command";
  version = "1";
  src = ./.;
  # vendor = ./prepared-vendor;
}
```

Vendor dependencies in `src/vendor` or supply `vendor`. The helper uses
`-mod=vendor`, runs `go test` and installs commands in `$out/bin`.
`subPackages` defaults to `[ "." ]`; use paths such as `[ "./cmd/my-command" ]`
for larger projects. Phase hooks and overrides work as for C recipes.
Set `doCheck = false` to skip tests.

For a shell, use `pkgs.mkShell { nativeBuildInputs = [ pkgs.go ]; }` and set
`GOCACHE` to a writable directory. Upstream tests that start HTTP servers need
loopback interfaces if networking has not configured them:

```sh
ip/ipconfig -P loopback /dev/null 127.1
ip/ipconfig -P loopback /dev/null ::1
```

Go's Plan 9 port has no cgo. Go HTTPS uses `/sys/lib/tls/ca.pem`;
Nix's webfs certificate pins apply separately.
