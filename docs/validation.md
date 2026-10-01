# Test coverage

The current suites passed on 2026-10-01 on Linux with KVM, using 9front release
11952. `flake.lock` pins the inputs; compiler patches live in
[pkgs/goken9cc](../pkgs/goken9cc).

- Compiler tests compare native, cross-compiled, and mixed objects, covering
  arguments, callbacks, structures, floating point, and varargs.
- Guest tests exercise installation, module lookup, file I/O, errors, and processes.
  Native builds use the image's libraries; cross builds use rebuilt libraries
  where configured.
- Library tests use known vectors and independent Python results for checksums,
  compression, and arithmetic. Generator checks compare output with the guest.
- Build checks cover executable format and archive handling.

Tests check exit status and expected results, use bounded waits, and discard VM
snapshot changes. File transfers use host loopback without forwarded guest
ports. The builds and tests work with the Nix sandbox enabled.

See [development](development.md) for commands and saved results, and
[toolchain limitations](feasibility.md#c-toolchain-status) for scope.
