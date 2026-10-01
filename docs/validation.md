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
| `nix build .#goken9cc` | Built the toolchain and checked archive creation, listing, and extraction with full-length member names. |
| `nix build .#hello-c-native` | Compiled and ran C in the guest, retrieved the binary, and checked its format. |
| `nix build .#hello-c-cross` | Compiled and linked C on Linux and checked its format. |
| `nix build .#sha1sum-tests -L` | Native and cross builds passed 46 checksum and error cases, with hashes checked against Python. |
| `nix build .#ape-tests -L` | Cross and guest `pcc` builds each passed four POSIX groups: memory, buffered I/O, descriptors and errno, and pipe/fork/exec/wait. |
| `nix build .#lua-tests -L` | Cross and guest builds each passed 11 Lua groups, including subprocess I/O and exit status. |
| `nix build .#libbz2-tests -L` | Seven groups passed in four native/cross archive and consumer combinations, with compressed bytes checked against Python. |
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

## Compiler comparison

`nix build .#c-abi-tests -L` passed on 2026-10-01 with the same pinned tools
and image. Six groups passed in each of four builds, for 24 group runs:

| Group | Coverage |
| --- | --- |
| Arguments and data model | Command-line arguments and scalar/pointer sizes. |
| Integer calls and recursion | Eight mixed-width arguments, signed values and recursive calls. |
| Pointers and callbacks | Array mutation and indirect calls across object boundaries. |
| Structures | Mixed-field structures passed and returned by value, with copy and pointer checks. |
| Floating point | Float and double arguments and returns, arithmetic and a double-to-64-bit-integer conversion. |
| Varargs and libc | Integer and float promotions, 64-bit values, pointers and libc formatting. |

The builds used native objects, cross-compiled objects, and both combinations
of a native object with a cross-compiled object. The fully cross-compiled binary
used the Linux linker; the other builds used 9front's linker. Each program
checked known expected values and exited successfully. All four produced the
same six result lines. No additional compiler patches were needed.

The build saves `results.json` in its Nix output. See
[compiler tests](development.md#compiler-tests) for the command and rerun options.
These tests cover selected ABI cases, not every type, instruction or library.

## Test behavior

The APE, Lua, and libbzip2 cross builds use rebuilt `libap` and `libbsd`; guest
builds use the image's libraries. The rebuilt `libap` matches all 291 archive
member names in the image.

The native Plan 9 C cross builds use rebuilt `libc`, matching the image's 263
archive member names. The C smoke test, checksum tests, and ABI suite pass with it.

Guest tests check exit status and expected output, use bounded waits, and discard
snapshot changes. Manual failure checks confirmed that the guest-control code
rejects nonzero exit status and missing output. It could still run subsequent
commands and shut down the guest.

Dependency checks confirmed that changing a package test leaves the sysroot
cached, while changing shared guest code invalidates it.

The upload and download servers bind to host loopback on an ephemeral port.
QEMU forwards no guest ports. Guest builds transfer files within the builder's
network namespace and work with the Nix sandbox enabled.

VM setup created a writable disk and refused to overwrite it. The launcher
rejected a missing disk. Logs normalize serial CR/CR/LF line endings so Nix
displays the guest output correctly.

These results cover the examples, APE API tests, sha1sum, Lua, and libbzip2. See
[toolchain limits](feasibility.md#c-toolchain-status) before using other packages.
