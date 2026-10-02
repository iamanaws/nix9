"""Check Nix signatures against host libsodium and exercise entropy failures."""

import base64
import ctypes
import os
import re


def sodium():
    lib = ctypes.CDLL(os.environ["SODIUM_LIBRARY"])
    lib.crypto_sign_seed_keypair.argtypes = [ctypes.c_void_p] * 3
    lib.crypto_sign_detached.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_void_p]
    lib.crypto_sign_verify_detached.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                              ctypes.c_ulonglong, ctypes.c_void_p]
    if lib.sodium_init() < 0:
        raise RuntimeError("host libsodium initialization failed")
    return lib


def key_fixtures(root):
    lib = sodium()
    public, secret = ctypes.create_string_buffer(32), ctypes.create_string_buffer(64)
    # Public RFC 8032 test key; never used outside this disposable test.
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    if lib.crypto_sign_seed_keypair(public, secret, seed) != 0:
        raise RuntimeError("host key generation failed")
    message = bytes(range(256)) * 256 + b"\0"
    values = [secret.raw, public.raw]
    for data in (b"", message):
        sig = ctypes.create_string_buffer(64)
        if lib.crypto_sign_detached(sig, None, data, len(data), secret) != 0:
            raise RuntimeError("host signing failed")
        values.append(sig.raw)
    if values[2].hex() != (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f"
        "b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    ):
        raise RuntimeError("host signature disagrees with RFC 8032")
    fixture, payload = root / "signing-keys", root / "signed-message"
    fixture.write_text("".join("test:" + base64.b64encode(value).decode() + "\n" for value in values))
    payload.write_bytes(message)
    return {fixture.name: fixture, payload.name: payload}


def check_keys(guest, root):
    output = guest.command("/tmp/libutil-probe keys /tmp/signing-keys /tmp/signed-message",
                           "libutil signatures PASS")
    values = {}
    for line in output.splitlines():
        if line.startswith(("PUBLIC ", "SIGNATURE ")):
            kind, encoded = line.split(" ", 1)
            name, value = encoded.split(":", 1)
            if name != "guest":
                raise RuntimeError("unexpected signing key name")
            values[kind] = base64.b64decode(value, validate=True)
    if len(values["PUBLIC"]) != 32 or len(values["SIGNATURE"]) != 64:
        raise RuntimeError("invalid guest key or signature length")
    message = (root / "signed-message").read_bytes()
    if sodium().crypto_sign_verify_detached(values["SIGNATURE"], message, len(message), values["PUBLIC"]) != 0:
        raise RuntimeError("host rejected guest signature")
    guest.command("/tmp/libutil-probe entropy", "entropy available")
    guest.command("mkdir -p /tmp/no-dev; echo -n > /tmp/empty-random")
    for source, target in (("/tmp/no-dev", "/dev"), ("/tmp/empty-random", "/dev/random")):
        output = guest.command(
            f"@{{ rfork n && bind {source} {target} && /tmp/libutil-probe entropy }}; "
            "echo entropy-status:$status", "entropy unavailable")
        if not re.search(r"(?m)^entropy-status:libutil-probe \d+: cc9exit=42$", output) \
                or "\nentropy available\n" in output:
            raise RuntimeError("key generation did not fail on unavailable entropy")
    return {"host_vectors": 2, "guest_signature_verified": True,
            "entropy_failures": ["missing device", "empty device"]}
