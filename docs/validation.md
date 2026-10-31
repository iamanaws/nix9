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
Add `--rebuild` to rerun a cached suite. `nix flake check` validates configuration
on the host and checks Go executable format. It does not run the guest suites.
Use `nix fmt` to format Nix files.

VM tests check exit status and expected results, enforce timeouts, and discard
snapshot changes. Transfers and test servers use host loopback. Tests also run
with the Nix sandbox enabled.

## Coverage

| Target | Checks |
| --- | --- |
| `c-abi-tests`, `ape-tests` | Native, cross and mixed objects; arguments, callbacks, structures, floating point, varargs and POSIX behavior. |
| `PACKAGE-tests` | Package behavior. Libraries use known vectors and independent Python results for hashes, compression and arithmetic. |
| `disk-archive-tests` | Native archive round trips, ownership and modes, filenames with spaces, empty files, SHA-256 vectors, corrupt checksums, truncated payloads, path traversal and missing source files. |
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
| `directory-tests`, `native-directory-tests` | Host/native declaration validation, checks without directory changes, parent creation, native ownership and permissions, conflicts, preserved contents, reboot recreation, rollback and removal. Host validation also runs in `nix flake check`. |
| `binding-tests`, `native-binding-tests` | Host/native binding validation, list ordering, replacement and unions, file creation routing, chained sources, private refresh, rollback, unavailable sources, manual conflicts, anchor cleanup, package references through GC, boot and removal. Host validation also runs in `nix flake check`. |
| `job-tests`, `native-job-tests` | Host/native schedule and relationship validation, native user execution, duplicate exclusion, live updates, logs, failure status, removal, rollback and command retention through GC. Host validation also runs in `nix flake check`. |
| `native-module-tests` | Offline host/native module evaluation, imports, typed options, overrides, merges, assertions and a composed system build. Samples native evaluation time and memory. |
| `native-machine-tests` | Two machines sharing runtime files with local writable stores; explicit initialization, independent generations, `newns`, reboot, rollback and boot-root retention through GC. |
| `native-ndb-tests` | Native NDB build, host and subnet queries on two machines, manual includes, invalid declarations, cs/DNS startup, disable and rollback across four boots. |
| `native-cpu-tests` | Native CPU init, startup namespace, DHCP/static IPv4, clock correction, logging, login, hook checks and retained generations. |
| `native-rcpu-tests` | Declarative CPU/auth services, dp9ik tickets and TLS, delegation and allowed-user policy, private runtime files, startup failure and recovery, client source export, native C build, persistent sessions, disable, rollback and reboot. |
| `native-graphical-tests` | Four machines with native Rio/Acme packages, a real framebuffer, shared-file editing, plumbing, remote Nix compilation, session cleanup, refresh, rollback and startup failures. Saves a screenshot. |
| `builder-tests`, `native-builder-tests` | Builder configuration validation and four-machine remote builds: authenticated input/output transfer, executable results, logs, system features, two-CPU scheduling, cancellation, failed outputs, denied credentials, offline result reuse and builder failover. Host validation runs in `nix flake check`. |
| `installation-tests` | Host evaluation of the bundled installation example, generated discovery and endpoints, stable identities, session dependencies and rejection of invalid inventories. Also runs in `nix flake check`. |
| `native-prebuilt-tests` | Build installation closures on one machine and import them on another; check/select without target configuration or builds, truncated transfers, missing or damaged dependencies, identity and runtime checks, preserved hooks and history, reboot, rollback and GC. |
| `native-deployment-tests` | Three-machine deployment over authenticated CPU sessions, live status, identity rejection, truncated imports and retries, prepared roots through GC, all-machine preflight, scheduler target readiness, local terminals, generation reuse, explicit reboot and rollback. |
| `native-sharing-tests` | The installation example on three machines with separate stores, native inventory validation and manifest builds, declared export directories, NDB discovery, TLS/9P exports, a union across two providers, creation routing and failed refresh recovery, delegated CPU access, terminal edits and a remote C build, permissions, unavailable providers, scheduled CPU jobs with provider failure/recovery, reboot and rollback. |
| `native-listen-tests` | Real TCP connections as `none`, booted-generation namespaces, manual services and namespaces, directory fallback, conflicts, persistent connections, EOF with webfs, removed ports, disable and rollback. |
| `network-tests`, `native-network-tests` | Host/native validation, DHCP, DNS override, static IPv4, multiple interfaces, primary-interface discovery, loopbacks, native NDB, gateway routing, interface removal, reboot and rollback. Configured boots run without harness networking. Host validation also runs in `nix flake check`. |
| `native-network-server-tests` | Five machines with an isolated Ethernet link, authenticated network-tree exports, terminal and delegated CPU access to a lab service, failed direct access, export permissions, read-only control rejection, provider address changes, reboot, rollback and recovery. |
| `storage-tests`, `native-storage-tests` | CWFS configuration validation and a five-machine workspace: independent storage boot, native 9P authentication, TLS export regression, builds on two CPU servers, dump history, file restoration, reboot persistence and policy rollback. Host validation runs in `nix flake check`. |
| `backup-tests`, `native-backup-tests` | Backup configuration validation and a six-machine installation: scheduled remote archives, native metadata, completed generations, overlap exclusion, failed runs, provider loss, checksum rejection and restoration onto empty replacement storage with the original server offline. Host validation runs in `nix flake check`. |
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
