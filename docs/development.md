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

Cross-builds use pinned sources and run on Linux without KVM.
Native bootstrap preparation and guest tests need KVM access for Nix builders.
`nix flake check` checks the Go executable format. Run the test targets to check
execution in the guest. Use `nix fmt` to format all Nix files.

## Measure native development

Run the benchmark from a checkout on persistent storage:

```sh
nix run .#benchmark-native -- nix9-performance
```

Choose a new output directory for each run. The benchmark creates a temporary
VM disk there, installs the bootstrap and measures downloads, extraction,
evaluation, source import, the first project build, cached builds and development
shells. It also checks that source edits rebuild, ignored files preserve cached
outputs, and restoring sources reuses the original output. Environment updates,
offline reboots, rollback and GC are checked too.
The VM disk is removed when the run exits. `timings.json` records completed
measurements; `results.json` is written only after all checks pass.
Times depend on host storage and load. Stop other VM tests when comparing runs.
The benchmark runs as an app so timing samples do not become nondeterministic
Nix build outputs.

## Toolchains

Cross-builds use Plan9port's `rc` and `mk`, goken9cc's `6c` and `6l`, and GCC
preprocessing for APE. Nix and its C++ dependencies use Clang, LLD and the cc9 runtime;
`elf2aout` converts the executable format. Go examples use `GOOS=plan9`.
Nix libraries and commands compile with `-O2`. Installed Nix commands omit symbol
tables; `nix build .#nix-util` retains the original ELF files for debugging.
Digest implementations also compile with `-O2`. Source imports grow their memory
buffer geometrically, avoiding repeated full-buffer copies with cc9's allocator.
Inputs are still hashed on each invocation; the configured NAR buffer limit
continues to determine when imports spill to disk.

Use `nix develop .#cross` for C development on Linux. In `examples/hello`, run
`mk` to build `6.out` for Plan 9. The shell keeps its sysroot and adapted
mkfiles in a temporary directory.

## Add a C package

`lib.callPackage ./package.nix { }` supplies `stdenv` and dependencies.
Cross and native builds share recipes such as [`mpc`](../pkgs/mpc/default.nix).
Use `buildPackages` for build tools and `buildInputs` for libraries.
APE packages use `pcc` with `libap` and `libbsd`.

The flake exports `lib.mkPlan9Program`:

```nix
mkPlan9Program {
  name = "my-program";
  sources = [ ./main.c ];
}
```

It uses the shared stdenv to compile, link with libc and install `bin/my-program`. Optional arguments are `includeDirs`, `libraries`
and `meta`. Pass rebuilt library packages through `libraries`.

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

Use `pcc -o program source.c` for POSIX C through APE. The wrappers use source-built
tools with installed headers and runtimes. `pcc` sets up a private
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

`pkgs.callPackage ./package.nix { }` supplies recipe dependencies; explicit arguments override them.

For an interactive C development shell in that project:

```rc
nix-shell
```

Run `mk` to build and `mk clean` to remove build outputs. Exit to restore the
original namespace, or use `nix-shell --run 'mk'` for one command.
Use `nix-shell default.nix` to enter a package's build environment without building it.
Use `--pure` to clear inherited variables and `--keep NAME` to retain one.
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

Run `$environment/session COMMAND ARGS...` for a private session, or omit the
command for an interactive rc shell. The optional `namespace` rc snippet runs
after activation. Session processes keep the environment rooted during GC.
Mounts disappear when the last process exits. Sourcing `activate` does not run
the snippet.

The bootstrap includes a [ramfs example](../examples/ramfs) that writes and reads
a file in a private memory filesystem:

```rc
nix-build $nix9/ramfs --out-link $roots/ramfs
environment=`{cat $roots/ramfs}
$environment/session rc $nix9/ramfs/run.rc
```

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
Packages use `stdenv.mkDerivation` with native rc, the C toolchain, libc and mk.
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
For Git sources, use `fetchgit { url = "…"; rev = "…"; hash = "sha256-…"; }`.
The revision must be a full 40-character commit hash reachable from the remote's refs.
The hash covers the exported tree. Symlinks and submodules are rejected.
Native `lua` builds against `liblua`. Both fetch the same pinned archive and
compile with APE.
Use `nix-native-tests` for native packages and shells, `nix-core-tests` for libraries
and commands, or `nix-store-tests` for transfers and caches. Store tests reuse the
native suite's exported closure. `nix-util-tests` runs all three.

### System configuration

The native package set provides `mkSystem` for a small machine configuration.
Start with [the example](../examples/system/configuration.nix), saved as
`configuration.nix` in the guest:

```nix
let
  pkgs = import <nix9>;
in
pkgs.mkSystem {
  hostName = "nix9";
  networking.enable = true;
  services.webfs.enable = true;
  packages = [ pkgs.fortune ];
  files."motd" = "Welcome to nix9.\n";
  # webfs.certificatePins."example.org" = [ "64 hexadecimal SHA-256 digits" ];
}
```

Activate the current bootstrap or a complete release containing `nix9-rebuild`,
then run:

```rc
nix9-rebuild build configuration.nix
nix9-rebuild switch configuration.nix
. /usr/local/pkg/nix9/system
fortune
cat /cfg/nix9/files/motd
nix9-rebuild list
nix9-rebuild rollback
. /usr/local/pkg/nix9/system
```

`build` retains its output at `/usr/local/nix/state/gcroots/system-build` without
selecting it. `switch` builds and checks activation in a private namespace before
selecting a generation at `/usr/local/nix/state/gcroots/system`. It sets
`/dev/sysname` immediately. Source `/usr/local/pkg/nix9/system` to refresh the
current shell's packages, configuration files and pins. Other existing sessions
keep their namespaces until refreshed. New login shells activate the selection.
Omitting the configuration argument uses `./configuration.nix`.

`hostName` is a lowercase DNS label, at most 63 characters. `packages` uses the
same collision checks and closure retention as `buildEnv`. `files` maps relative
paths to text, exposed under `/cfg/nix9/files` in the session namespace. Native
machine startup files such as `/cfg/nix9/termrc` remain visible. Paths cannot
escape that directory or overlap a parent file. Removing a file from the next
configuration removes it from the managed view. Store references in file contents
retain their dependencies through GC.

`webfs.certificatePins` maps lowercase DNS hosts or IPv4 addresses to nonempty
lists of 64-digit SHA-256 hex fingerprints. These become native
`x509 sha256=...` records, bound before `/sys/lib/tls/webfs/hosts`. They override
the same host's existing file in that namespace. Removing a declared host
reveals any underlying manual policy. Other host files and the existing
`revoked` file remain in place. Activation creates an empty revocation file if
one is missing. Keep revocations configured as described below.
Enable `services.webfs` as described below to start it with these pins and
replace its policy namespace when refreshing into a different generation.
Restart a manually started webfs yourself to use new pins.

The first switch installs wrappers for `/rc/bin/termrc.local` and
`/rc/lib/rcmain.local`. Existing scripts are retained with a `.nix9-original`
suffix and run before the managed hook. Later switches reject edited or removed
wrappers. Terminal boot sets the hostname and retains the booted generation at
`system-boot`; terminal and login activation expose the managed environment.
This version targets terminal systems. CPU-server startup,
general service management, kernel builds and disk configuration are separate work.

`rollback` selects the previous retained generation and applies its hostname;
refresh the session afterward. Use `nix9-rebuild delete NUMBER` to release an
inactive generation. The selected and booted generations cannot be deleted.
After rebooting into the selected generation, an older booted generation can be
deleted and collected. Refresh sessions before deleting generations they use;
automatic runtime root discovery is not available.

System changes use the kernel service lock `#s/nix9-system`. An interrupted
command may leave this marker. Remove it only after confirming no rebuild is
running. Abrupt power loss during the first hook installation or profile writes
is not covered by the update checks.
System configuration and Nix release selection have separate profiles:
continue using the complete-release workflow above to update Nix itself.

### System networking

`networking.enable = true` configures `/net/ether0` with DHCP at terminal boot,
including native lease renewal, the offered gateway and DNS servers. Networking
is unmanaged by default. `networking.interface` selects another Ethernet device,
such as `ether1`. One primary interface is supported.

For static IPv4, replace the DHCP configuration with:

```nix
networking = {
  enable = true;
  useDHCP = false;
  address = "192.168.1.42";
  prefixLength = 24;
  defaultGateway = "192.168.1.1";
  nameservers = [ "192.168.1.1" ];
};
```

Static configuration requires an address and an integer prefix length from 1 to
32; the gateway is optional for a local network. DHCP cannot be combined with
an address or prefix. IPv4 addresses use decimal octets without leading zeros.
Ethernet addresses and gateways exclude loopback, unspecified and multicast
ranges. DNS servers may use IPv4 loopback. External IPv6 configuration is not
provided yet.

Enabled networking also configures `127.0.0.1` and `::1`, then starts native
`ndb/cs` and `ndb/dns -r`. `ipconfig` writes the primary address, mask, gateway
and DHCP information to `/net/ndb`; `/lib/ndb/local` is preserved. Explicit
`nameservers` override DHCP DNS through the resolver's `DNSSERVER` environment
setting, including after lease renewal. DHCP metadata in `/net/ndb` still records
the offered servers. An empty list uses the native NDB/DHCP settings. The managed
resolver clears inherited `DNSSERVER` and `DOTSERVER` settings before applying
the configuration.

Network changes take effect after reboot, including rollback. `switch` and
sourcing `/usr/local/pkg/nix9/system` leave the running interfaces and resolver
alone. Boot applies the network before activating the session namespace, so
other terminal processes inherit the connection and DNS services. Remove
conflicting manual interface setup from startup scripts before enabling this;
starting `cs` or `dns` before the managed boot hook causes a visible networking
error. Startup errors are printed on the console and terminal boot continues.
Disabling managed networking returns the next boot to native 9front startup;
it does not promise an offline machine.

### Managed webfs

`services.webfs.enable = true` starts the bootstrap's bundled `webfs` after
activating the system's certificate pins. It is disabled by default and does
not require managed networking if the network is configured another way.
HTTP is available immediately in the activated namespace; HTTPS also requires
the appropriate `webfs.certificatePins` or existing manual trust policy.

Terminal boot and login activation start the service. After `switch` or
`rollback`, source `/usr/local/pkg/nix9/system` to update the current session.
A different generation or bootstrap starts a new server with the current TLS
namespace. Repeated activation of the same generation reuses the server.
Other sessions retain their own mounts and trust policy until refreshed.
Changes to the shared revocation file still take effect on existing connections.

The service mounts at `/mnt/nix9-webfs` and overlays `/mnt/web` in the session's
private namespace. Disabling it removes its mounts and reveals any inherited
manual webfs. It does not stop servers used in other namespaces. An activation
check rejects manually replaced managed mounts, an occupied private webfs mount
or a preexisting rc function named `webfs`. Rebuild preflight checks these
conditions without starting a daemon or replacing the caller's mounts.

Managed activation supplies a small rc function that makes bare `webfs` startup
idempotent, including glenda's usual login profile. Calls with explicit arguments
still run the bundled program. To change the managed mount, update the system
configuration rather than mounting another server over it. The private mount
point is reserved while the service is enabled.

The current bootstrap also removes its managed overlay when refreshing into an
older generation that predates services. Such generations retain their manual
startup behavior. A rescue shell created after a failed graphical session is
outside the boot activation namespace; source `/usr/local/pkg/nix9/system`
there, as for the managed package environment.

### Native Go

The optional Go bootstrap includes pinned Go 1.26.7 sources and a cross-built
seed compiler. The usual `native-bootstrap` stays focused on C development.
Build the Go archive on Linux and install it using the same steps as the
README quick start, substituting this archive:

```sh
nix build .#native-go-bootstrap -o result-native-go-bootstrap
```

If a complete release is already selected, first upgrade it with
`/usr/local/pkg/nix9/release.nix` and `nix-profile`, as described above.
Unpacking a bootstrap archive preserves the existing release selection.

Activate that installation in the guest, then rebuild Go through native Nix:

```rc
. /usr/local/pkg/nix9/activate
roots=/usr/local/nix/state/gcroots
nix-build $nix9/packages -A go --out-link $roots/go
go=`{cat $roots/go}^/bin/go
$go version
```

The compiler and tools build inside 9front using the upstream `make.rc` script.
Local source and seed archives are imported with fixed-output hashes, so
evaluation does not need to hash their contents on every invocation.
The resulting toolchain has no runtime reference to the seed compiler.
Build caches and temporary files live in the build directory. Automatic toolchain
downloads, module proxies and checksum-service lookups are disabled.
Use a VM with 4 GiB of memory for the native build and tests.
Upstream tests that start local HTTP servers also need loopback interfaces:

```rc
ip/ipconfig -P loopback /dev/null 127.1
ip/ipconfig -P loopback /dev/null ::1
```

The Go package set provides `buildGoModule` for command packages. For a project
with a `go.mod`, use:

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

Dependencies must already be vendored in `src/vendor`, or supplied as a prepared
directory through `vendor`. The helper builds with `-mod=vendor`, runs `go test`
and installs commands into `$out/bin`. `subPackages` defaults to `[ "." ]`;
set it to paths such as `[ "./cmd/my-command" ]` for larger projects.
Normal phase hooks and overrides remain available. Set `doCheck = false` to
skip package tests.

For a development shell, use `pkgs.mkShell { nativeBuildInputs = [ pkgs.go ]; }`
and set `GOCACHE` to a writable directory. Go's Plan 9 port does not support
cgo. Go HTTPS applications use `/sys/lib/tls/ca.pem` for CA certificates;
webfs certificate pins configure Nix downloads separately.
`native-go-tests` covers bootstrap compilation, the native rebuild, selected
standard-library tests, package builds, development shells, signed substitution,
seed collection and compilation after an offline reboot.

### Trust HTTPS servers

The Nix package and complete releases include a rebuilt `webfs` with explicit
host-bound certificate trust. Before fetching HTTPS sources or using an HTTPS
cache, configure `/sys/lib/tls/webfs`. Obtain the server's leaf certificate through
a trusted channel and compute its SHA-256 fingerprint over the DER certificate.
For a PEM certificate on Linux, run from `nix develop`:

```sh
openssl x509 -in server.pem -outform DER | openssl dgst -sha256
```

On 9front, substitute that 64-digit hex fingerprint below:

```rc
mkdir -p /sys/lib/tls/webfs/hosts
if(! test -e /sys/lib/tls/webfs/revoked) echo -n > /sys/lib/tls/webfs/revoked
echo 'x509 sha256=FINGERPRINT' >> /sys/lib/tls/webfs/hosts/example.org
webfs -m /mnt/web -T 60000
```

Retain existing revocations when adding hosts. Host filenames use lowercase
ASCII/IDNA names or IP literals, without a port or trailing dot. Pins apply to
all ports for that host.
Each non-comment line is `x509 sha256=` followed by 64 hex digits. Several pins
can be listed for certificate rotation. Revoke a certificate by adding the same
record to `revoked`; revocation takes precedence for every host. Keep these files
writable only by the person managing trust.

The pin binds the exact leaf certificate to the host named by the file. This
policy does not use CA chains, certificate subject names or validity dates.
Trust files use the native thumbprint record format with SHA-256 certificate
hashes; SHA-1, SPKI pins and `#include` records are not accepted. Each file is
limited to 64 KiB. Missing, unreadable or malformed policy files reject HTTPS.
An empty host file also rejects that host. HTTP downloads need no TLS policy.

Webfs reads the policy on connection establishment and before pooled connections
are reused. A redirect to another HTTPS host requires that host's own pin;
HTTPS-to-HTTP redirects are rejected. `webfs -t /absolute/policy` selects a
different directory for a mounted service. Native `fetchurl` and `fetchgit`
builders use the default directory. Remount with the bundled `webfs` after
upgrading an older installation that already has `/mnt/web` mounted.
Nix checks the `tls-pins sha256-cert-v1` control message before HTTP or HTTPS
downloads and rejects a legacy webfs mount. HTTP requests require the same
transport because they can redirect to HTTPS.

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
transport and uses the [host trust policy](#trust-https-servers) above. Cache
signatures and content hashes are checked in addition to the TLS pin. The
bootstrap archive configures its bundled file cache.
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
