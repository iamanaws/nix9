# Test coverage

The suites run on Linux with KVM and 9front release 11952. `flake.lock` pins
the inputs. Compiler patches are in
[pkgs/goken9cc](../pkgs/goken9cc).

- Compiler tests compare native, cross-compiled, and mixed objects. They check
  arguments, callbacks, structures, floating point, and varargs.
- Guest tests exercise installation, module lookup, file I/O, errors, and processes.
  Native compiler baselines use the image's libraries. Cross and development
  builds use rebuilt libraries where configured.
- Library tests use known vectors and independent Python results for checksums,
  compression, and arithmetic. Generator checks compare output with the guest.
- Build checks cover executable format and archive handling. Native Nix tests
  cover toolchain bootstrapping, derivation paths, dependency builds, fixed hashes,
  multiple outputs, partial rebuilds and rebuild checks, cancellation cleanup,
  profile generations, permanent roots and garbage collection.
  Guest development tests build native and POSIX C, including Lua, with the
  image's headers and libraries hidden.

Tests check exit status and expected results, set timeouts, and discard VM
snapshot changes. Transfers use host loopback. The two-VM cache test forwards
one loopback-only port for read-only 9P and checks reuse after the server stops.
HTTP(S) cache tests check signatures, damaged downloads, redirects and repair.
`webfs-tests` builds the transport on Linux and inside 9front. Both builds check
host-bound certificate pins, unknown and wrong hosts, live revocation and pin
removal on pooled connections, redirect trust, HTTPS downgrade rejection and
malformed or missing policy files. Nix file/archive fetches, native `fetchurl`
and HTTPS cache substitution reject untrusted and revoked certificates.
Proxy tests authenticate HTTPS proxies and destination servers independently,
including revocation on reused tunnels.
Legacy image webfs mounts are rejected before Nix sends HTTP or HTTPS requests.
The `native-bootstrap-tests` target checks the signed cache in a clean VM, then builds
a C project and tests environment updates and rollback after GC.
`native-release-tests` checks complete release selection, offline reboots and rollback.
`native-system-tests` builds machine configurations with packages, hostname,
generated files and webfs pins. It checks activation before selection, invalid
configuration and failed-update rejection, preservation of terminal and login
hooks, edited-hook rejection, generation reuse, offline terminal boots and
logins, rollback and GC retention of the booted generation. It does not cover
CPU-server startup or abrupt power loss while installing hooks or selecting a profile.
`native-network-tests` boots four times with the harness's interface setup
disabled. It checks DHCP defaults, an explicit DNS override despite an offered
DHCP resolver, static IPv4, both loopbacks, preservation of `/lib/ndb/local`,
native `/net/ndb` records and DNS resolution through a local authoritative test
server. HTTP downloads use a QEMU guest forwarding address outside the static
guest's subnet, exercising its default gateway without public network access.
Switching and rollback leave the running network intact; reboot restores the
selected configuration. Invalid networking configurations must fail without
changing the selected generation. These tests cover one Ethernet interface,
not external IPv6 or DHCP renewal across lease expiration. Run it with
`nix build .#native-network-tests`.
`native-services-tests` checks managed webfs activation, repeated activation and
bare startup, HTTP/HTTPS and native Nix fetches, pin changes and rollback, login
namespace isolation, disabling the overlay and selecting a generation predating
services. Two subsequent boots fetch without manual interface or service setup.
The VM uses a headless terminal profile in place of rio; its bare webfs invocation
also checks compatibility with glenda's startup behavior. All HTTP and TLS servers
run on host loopback. Run it with `nix build .#native-services-tests`.
`native-timesync-tests` boots RTC UTC, NTP, RTC local-time and unmanaged
configurations. A host-loopback UDP NTP fixture supplies a clock two minutes ahead;
the guest must contact it and correct its clock. The suite checks exactly one
timesync process, no service replacement during switching or login, rollback on
reboot, restoration of native startup when management is disabled, and rejection
of invalid settings. It does not use a public time server. Run it with
`nix build .#native-timesync-tests`.
`native-update-tests` fetches pinned recipes, builds an update, rejects failed updates
and checks offline rebuilding and rollback after GC.
`native-reproducibility-tests` compares toolchain NARs from two clean VMs without substitutions.
`native-go-tests` uses the optional Go bootstrap in a 4 GiB VM. It checks the seed
compiler inside a Nix build, rejects a wrong local archive hash, rebuilds Go 1.26.7
natively, then collects the seed.
Package tests exercise Unicode, files and subprocesses. Selected upstream
standard-library tests, a rebuild comparison, development shells, signed cache
substitution and compilation after an offline reboot use the rebuilt compiler.
These checks do not cover the full upstream Go suite or cgo.
Evaluator fetch tests cover file and archive hashes, relative imports, executable
bits, malformed archives, path confinement, pure evaluation and offline reuse.
The builds and tests work with the Nix sandbox enabled.

The [native development benchmark](development.md#measure-native-development)
uses a persistent disk on the output filesystem and checks project builds,
source edits, ignored files, restoration of previous sources,
environment upgrades, rollback and GC across offline reboots. It records timing
samples separately from the reproducible test outputs.

See [development](development.md) for commands and saved results, and
[toolchain limitations](feasibility.md) for scope.
