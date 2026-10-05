# Test coverage

The suites run on Linux with KVM, using 9front release 11952. `flake.lock` pins the inputs; compiler patches live in
[pkgs/goken9cc](../pkgs/goken9cc).

- Compiler tests compare native, cross-compiled, and mixed objects, covering
  arguments, callbacks, structures, floating point, and varargs.
- Guest tests exercise installation, module lookup, file I/O, errors, and processes.
  Native compiler baselines use the image's libraries; cross and development builds
  use rebuilt libraries where configured.
- Library tests use known vectors and independent Python results for checksums,
  compression, and arithmetic. Generator checks compare output with the guest.
- Build checks cover executable format and archive handling. Native Nix tests
  cover derivation paths, dependency builds, fixed hashes, multiple outputs and partial rebuilds,
  cancellation cleanup, permanent roots and garbage collection.
  Guest development tests build native and POSIX C, including Lua, with the
  image's headers and libraries hidden.

Tests check exit status and expected results, use bounded waits, and discard VM
snapshot changes. Transfers use host loopback; the two-VM cache test forwards
one loopback-only port for read-only 9P and checks reuse after the server stops.
The builds and tests work with the Nix sandbox enabled.

See [development](development.md) for commands and saved results, and
[toolchain limitations](feasibility.md) for scope.
