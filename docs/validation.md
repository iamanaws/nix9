# Test results

All checks below passed on 2026-10-01 on x86_64 Linux with KVM and Nix 2.34.8.
The guest was 9front release 11952, amd64/hjfs. Builds used Go 1.26.7 and
QEMU 10.2.4. `flake.lock` records the exact source revisions, including goken9cc.
The compiler also uses the patches in `pkgs/goken9cc`.

## Builds and guest tests

| Command | Result |
| --- | --- |
| `nix build .#hello-plan9` | Cross-compiled the Go example. |
| `nix flake check -L` | Validated the Go binary's Plan 9 amd64 header and text section. |
| `nix build .#vm-image` | Fetched the hash-verified image and prepared its serial console. |
| `nix build .#sysroot` | Extracted `sys/include`, `amd64/include`, and `amd64/lib`. |
| `nix build .#goken9cc` | Built the patched compiler, assembler, and linker on Linux. |
| `nix build .#hello-c-native` | Compiled and ran C in the guest, retrieved the binary, and checked its format. |
| `nix build .#hello-c-cross` | Compiled and linked C on Linux and checked its format. |
| `nix run .#smoke-test` | Ran the Go binary in a fresh guest. |
| `nix run .#smoke-test-c` | Ran the retrieved guest-built C binary in a fresh guest. |
| `nix run .#smoke-test-c-cross` | Ran the cross-compiled C binary in a fresh guest. |

Both C binaries passed file create/write/seek/read/remove and
pipe/fork/exec/wait checks. Each printed:

```text
PASS: C file create/write/seek/read/remove
PASS: C pipe/fork/exec/wait
Hello from Nix-built C on 9front/amd64!
```

## Test behavior

Guest tests check exit status and expected output, use bounded waits, and discard
snapshot changes. Manual failure checks confirmed that the guest-control code
rejects nonzero exit status and missing output. It could still run subsequent
commands and shut down the guest.

The upload and download servers bind to host loopback on an ephemeral port.
QEMU forwards no guest ports. Guest builds transfer files within the builder's
network namespace and work with the Nix sandbox enabled.

VM setup created a writable disk and refused to overwrite it. The launcher
rejected a missing disk. Logs normalize serial CR/CR/LF line endings so Nix
displays the guest output correctly.

These results cover the example programs. See
[toolchain limits](feasibility.md#c-toolchain-status) before using other packages.
