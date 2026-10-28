# Downloads and caches

Native Nix uses the bundled webfs for HTTP and HTTPS. Start it manually with
`webfs -m /mnt/web -T 60000`, or enable [managed webfs](services.md#webfs).
An old image's webfs is rejected before either kind of request because HTTP
can redirect to HTTPS. After upgrading, remount with the bundled version.

## HTTPS trust

Webfs pins the exact leaf certificate to a host. It does not validate CA chains,
certificate names or validity dates. Obtain the certificate through a trusted
channel. For a PEM file on Linux, run from `nix develop`:

```sh
openssl x509 -in server.pem -outform DER | openssl dgst -sha256
```

In the guest, replace `FINGERPRINT` with that 64-digit hex value:

```rc
mkdir -p /sys/lib/tls/webfs/hosts
if(! test -e /sys/lib/tls/webfs/revoked) echo -n > /sys/lib/tls/webfs/revoked
echo 'x509 sha256=FINGERPRINT' >> /sys/lib/tls/webfs/hosts/example.org
```

Host filenames are lowercase ASCII/IDNA names or IP literals, without a port or
trailing dot. Each pin applies to all ports for that host. List several records
for certificate rotation. Add the same record to `revoked` to reject it for every
host; revocation takes precedence. Preserve existing revocations and restrict
write access to the trust administrator.

Each file is limited to 64 KiB. Records must use `x509 sha256=` and 64 hex digits;
SHA-1, SPKI and `#include` are unsupported. Missing, unreadable or malformed
policy files reject HTTPS, as does an empty host file. HTTP needs no trust policy.

Webfs checks policy when connecting and before reusing connections. Redirects
to another HTTPS host need that host's pin; HTTPS-to-HTTP redirects fail.
`webfs -t /absolute/policy` selects another policy directory. Native fetch
builders use the default directory. For declarative pins, see
[system configuration](configuration.md#machine-settings).

## Source fetches

Configure networking and mount webfs before fetching. The native package set
provides:

| Fetcher | Hash and restrictions |
| --- | --- |
| `fetchurl { url = "URL"; hash = "sha256-..."; }` | Checks the downloaded file. |
| `builtins.fetchurl { url = "URL"; sha256 = "sha256-..."; }` | Fetches a file during evaluation. |
| `builtins.fetchTarball { url = "URL"; sha256 = "sha256-..."; }` | Hashes the unpacked tree and strips a single enclosing directory. |
| `fetchgit { url = "URL"; rev = "COMMIT"; hash = "sha256-..."; }` | Hashes the exported tree. Requires a full 40-character commit reachable from remote refs; rejects symlinks and submodules. |

Pinned evaluator files and trees can be reused offline. Archive extraction
accepts regular files and directories, rejecting links and duplicate files.
`builtins.fetchGit` and flakes are unavailable.

## Binary caches

For a trusted transfer between machines with the same store path:

```rc
nix-store --export `{nix-store -qR $result} > /tmp/closure.export
```

Copy that file to the destination and run `nix-store --import < /tmp/closure.export`.
[Root the imported output](native.md#store-maintenance) before GC.

For automatic substitution, configure `substituters` and `trusted-public-keys`
with a cache URL and its public signing key. Supported URLs include:

- `file:///path/to/cache?store=/usr/local/nix/store`, including a read-only 9P mount.
- `https://cache.example?store=/usr/local/nix/store`, or HTTP.

`nix-store --realise` fetches missing outputs and dependencies, verifying
signatures and content hashes. HTTPS also checks the host's certificate pin.
Network caches are read-only. The bootstrap configures its bundled file cache.

To publish a local cache:

```rc
nix-store --generate-binary-cache-key NAME SECRET PUBLIC
cache='file:///path/to/cache?store=/usr/local/nix/store&secret-key=/path/to/SECRET'
nix-store --store $cache --import < /tmp/closure.export
```

Share the cache and public key; keep the secret key private.
See [store maintenance](native.md#store-maintenance) for verification and repair.
