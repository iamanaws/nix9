"""Explicit certificate trust for the disposable guests' HTTPS fixtures."""

import hashlib
from pathlib import Path
import ssl
import re


TRUST = "/sys/lib/tls/webfs"


def certificate_pin(certificate):
    der = ssl.PEM_cert_to_DER_cert(Path(certificate).read_text())
    return "x509 sha256=" + hashlib.sha256(der).hexdigest()


def trust_certificate(guest, certificate, host="10.0.2.2", *, directory=TRUST):
    pin = certificate_pin(certificate)
    guest.command(f"mkdir -p {directory}/hosts; echo -n > {directory}/revoked; echo '{pin}' > {directory}/hosts/{host}")
    return pin


def reject_certificates(guest, certificate, command, host="10.0.2.2", *, directory=TRUST):
    """Use distinct uncached inputs for each TLS failure via @CASE@ in command."""
    pin = certificate_pin(certificate)
    try:
        for label, reason in (("untrusted", "not trusted"), ("revoked", "revoked")):
            trusted = "x509 sha256=" + "0" * 64 if label == "untrusted" else pin
            guest.command(f"echo '{trusted}' > {directory}/hosts/{host}")
            guest.command(f"echo -n > {directory}/revoked" if label == "untrusted"
                          else f"echo '{pin}' > {directory}/revoked")
            result = guest.command(command.replace("@CASE@", label) + "; echo TLS-ERROR:$status")
            if not re.search(r"(?m)^TLS-ERROR:.+$", result) or reason not in result:
                raise RuntimeError(f"Nix accepted a {label} certificate: {result}")
    finally:
        guest.command(f"echo '{pin}' > {directory}/hosts/{host}; echo -n > {directory}/revoked")
