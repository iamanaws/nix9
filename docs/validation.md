# Tests

Tests run on x86_64 Linux with KVM and the pinned 9front release 11952.
Both your user and Nix builders need `/dev/kvm`. Cross-builds alone do not need it.
Run commands from the checkout:

```sh
nix flake show
nix build .#native-listen-tests -o result-tests -L
```

Replace the target with a suite below, or `PACKAGE-tests` when available.
Suites save JSON results under their output; most use `results.json`.
Add `--rebuild` to rerun a cached suite. `nix flake check` checks Go executable
format; it does not run the guest suites. Use `nix fmt` to format Nix files.

VM tests check exit status and expected results, enforce timeouts, and discard
snapshot changes. Transfers and test servers use host loopback. Tests also run
with the Nix sandbox enabled.

## Coverage

| Target | Checks |
| --- | --- |
| `c-abi-tests`, `ape-tests` | Native, cross and mixed objects; arguments, callbacks, structures, floating point, varargs and POSIX behavior. |
| `PACKAGE-tests` | Package behavior. Libraries use known vectors and independent Python results for hashes, compression and arithmetic. |
| `package-tests`, `guest-development-tests` | Archive installation and native/APE C builds, including Lua, with image headers and libraries hidden. |
| `nix-core-tests` | Nix libraries, commands, NARs, process handling and store primitives. |
| `nix-native-tests` | Toolchain bootstrap, dependency builds, fixed hashes, multiple outputs, partial rebuilds, rebuild comparisons, cancellation, profiles, roots and GC. |
| `nix-fetch-tests` | Evaluator file/archive hashes, relative imports, executable bits, malformed archives, path confinement, pure evaluation and offline reuse. |
| `nix-store-tests` | Signed caches, transfers, repair and recovery. Includes two-VM read-only 9P reuse after the server stops, and HTTP(S) failure cases. |
| `nix-util-tests` | Aggregates the four preceding Nix suites. |
| `native-bootstrap-tests` | Signed cache installation in a clean VM, C development, environment updates and rollback after GC. |
| `native-release-tests`, `native-update-tests` | Release and recipe updates, failed updates, offline rebuilding, reboot, rollback and GC retention. |
| `native-reproducibility-tests` | Toolchain NAR comparison across two clean VMs without substitution. |
| `native-system-tests` | Configuration validation, activation preflight, hook preservation and edit rejection, generation reuse, terminal boot, login, rollback and boot roots. |
| `native-module-tests` | Offline host/native module evaluation, imports, typed options, overrides, merges, assertions and a composed system build. Samples native evaluation time and memory. |
| `native-machine-tests` | Two machines sharing runtime files with local writable stores; explicit initialization, independent generations, `newns`, reboot, rollback and boot-root retention through GC. |
| `native-ndb-tests` | Native NDB build, host and subnet queries on two machines, manual includes, invalid declarations, cs/DNS startup, disable and rollback across four boots. |
| `native-cpu-tests` | Native CPU init, startup namespace, DHCP/static IPv4, clock correction, logging, login, hook checks and retained generations. |
| `native-rcpu-tests` | Declarative CPU/auth services, dp9ik tickets and TLS, delegation and allowed-user policy, private runtime files, startup failure and recovery, client source export, native C build, persistent sessions, disable, rollback and reboot. |
| `native-sharing-tests` | Three machines with separate stores, NDB discovery, authenticated TLS/9P exports, delegated CPU access, terminal edits and a remote C build, permissions, session mounts, unavailable providers, disable, reboot and rollback. |
| `native-listen-tests` | Real TCP connections as `none`, booted-generation namespaces, manual services and namespaces, directory fallback, conflicts, persistent connections, EOF with webfs, removed ports, disable and rollback. |
| `native-network-tests` | DHCP, DNS override, static IPv4, loopbacks, native NDB, gateway routing, reboot and rollback. Harness networking is disabled. |
| `native-services-tests` | Webfs startup, idempotence, HTTP/HTTPS, pin changes, session isolation, disable and boot without manual setup. |
| `native-timesync-tests` | RTC UTC/local time, NTP correction through a local fixture, one client, append-only correction logs, rollback and native startup restoration. |
| `native-logging-tests` | File validation, nontruncating preparation, modes, event order, failed selection, reboot, rollback and retained history. |
| `webfs-tests` | Cross and native transports, host-bound TLS pins, live revocation, pooled connections, redirects, downgrade rejection, proxy authentication and legacy-mount rejection. |
| `native-go-tests` | Seed compilation, native Go rebuild, selected upstream tests, vendored packages, shells, signed substitution, seed GC and offline compilation. |
| `native-shell-tests`, `native-patch-tests`, `native-ramfs-tests` | Shell inputs, patch phases and private ramfs sessions. |
| `native-git-tests`, `native-clone-tests` | Pinned Git fetches and building from a native clone. |

Compiler tests use image libraries as native baselines; cross and development
builds use rebuilt libraries where configured.

Go checks omit the full upstream suite and cgo. See
[verification limits](feasibility.md#verification-limits) for other gaps.
Test implementations live in [tests](../tests).

## Native development benchmark

```sh
nix run .#benchmark-native -- nix9-performance
```

Use a new directory on persistent storage for each run. The benchmark measures
bootstrap transfer and extraction, evaluation, source import, first/cached builds
and shells. It checks source edits, ignored files, restored-source reuse,
environment updates, offline reboots, rollback and GC.

A temporary VM disk lives on that filesystem and is removed on exit.
`timings.json` retains completed measurements; `results.json` appears only after
all checks pass. Stop other VM tests when comparing runs. Timing runs use an app
rather than nondeterministic Nix build outputs.
