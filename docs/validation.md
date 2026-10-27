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
The `native-bootstrap-tests` target checks the signed cache in a clean VM, then builds
a C project and tests environment updates and rollback after GC.
`native-release-tests` checks complete release selection, offline reboots and rollback.
`native-update-tests` fetches pinned recipes, builds an update, rejects failed updates
and checks offline rebuilding and rollback after GC.
`native-reproducibility-tests` compares toolchain NARs from two clean VMs without substitutions.
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
