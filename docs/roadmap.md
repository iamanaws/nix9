# System roadmap

Updated 2026-10-28. The first three milestones and the CPU/authentication portion
of milestone 4 are implemented. See [configuration](configuration.md),
[discovery](discovery.md), [access](access.md) and [tests](validation.md).

## Goal and design

Describe a Plan 9 installation with Nix, including its machines, shared services
and namespace policies. The first demonstration uses three 9front VMs: a combined
file/auth server, a CPU server and a terminal. Start with existing bootable systems.

- Keep `mkSystem` for one machine. Add composable role modules and an eventual
  `mkInstallation` builder.
- Use a small core and explicit imports for optional modules. Use the pinned Nix
  module library and bundle what native evaluation needs for offline use.
- Separate configuration generation from startup, with explicit package and
  startup dependencies. Add provider abstractions when a second implementation
  needs them.
- Derive NDB entries, service locations and deployment targets from one inventory.
  Roles compose, so file and authentication services can share a machine.
- Give each machine a stable identity, separate from its mutable hostname. Give
  machines, service processes and user sessions their own namespace policies.
- Use native boot hooks, listeners, factotum, 9P and rc. Package service binaries
  and their dependencies so generations select their versions.
- Keep writable Nix stores and databases local initially. Share projects, user
  data and a signed read-only package cache through file services. The current
  [store locks](../pkgs/nix/store-platform.cc) require a common kernel service namespace.
- Declare persistent paths, owners and runtime key references. Private keys stay
  outside derivations. Configuration rollback does not restore mutable data.

## Milestones

### Completed foundations

| Milestone | Delivered |
| --- | --- |
| 1. Module foundation | Bundled pinned Nix module library, composable `mkSystem`, offline host/native evaluation, typed options, overrides and merge checks. Native tests sample evaluation time and memory. |
| 2. Machine identity and state | Explicit initialization, stable IDs, machine-specific generations and locks, and local writable Nix mounts restored before activation and after `newns`. Two-machine tests cover independent selections, reboot, rollback and GC. |
| 3. Native discovery | Packaged NDB tools and dependencies, host/network records, ordered manual includes and boot-selected cs/DNS. Tests cover discovery, validation, DNS disable and rollback. |

### 4. Add native roles and namespace resources

CPU access and authentication modules now use packaged native services, with
explicit access policy and runtime keys. Next, add file exports around an existing
filesystem and terminal sessions, packaging the remaining tools they need.

Describe named resources, their providers, imports, bind order and required or
optional availability. Separate boot, service and session namespaces. Add explicit
filesystem account management.

Acceptance: the three VMs use actual authentication tickets, shared project files
and a remote C build. Check access rejection, missing providers, repeated startup,
reboot and rollback.

### 5. Build and deploy an installation

Add `mkInstallation` to produce shared discovery data, per-machine closures and
a manifest of identities, endpoints and dependencies. Validate the graph before
deployment. Keep host and native entry points usable without guest flakes.

Add selection of an already-realised system closure. Stage closures through
[signed caches or authenticated transfers](transport.md#binary-caches), validate
them on targets, then use `rcpu` to select and check each machine. Order provider
changes before consumers where required, preserve compatibility during rollout,
and identify changes requiring reboot. Record intended and observed generations.

Acceptance: an interrupted transfer changes no selection; a failed health check
halts dependent changes and reports partial deployment. Rollback is explicit and
per machine. Retain closures needed by running services and sessions; automatic
runtime root discovery is not assumed. Test deployment again after reboot.

### 6. Make the installation useful day to day

Add native scheduled maintenance, log handling, filesystem dumps and restoration
checks. Native cron's authentication-server placement and remote execution need
their own tests. Add a terminal workspace with rio, acme and plumber, including
their graphical libraries and data packages.

Acceptance: a declared maintenance job runs on its target host; a restore check
reads saved data; a graphical terminal uses shared project files and remote CPU
tools with its declared package and namespace environment.

## Deferred scope

Full build isolation, shared writable stores and distributed GC, generic daemon
supervision, automated disk provisioning, kernel builds and network-root boot
generation follow separate proposals. Initial deployment uses existing kernels
and bootstraps. It provides ordered machine updates, without claiming an atomic
transaction across the installation.
