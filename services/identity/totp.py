"""TOTP (RFC 6238) implementation for Kian Trading Intelligence.

Uses HMAC-SHA1 with a 30-second time step (stdlib only — no external deps).
Provides secret generation, provisioning URI, verification with window
support, and a helper to get the current code for testing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote, urlencode

TOTP_TIME_STEP = 30  # seconds per time step (RFC 6238)
TOTP_DIGITS = 6  # 6-digit code
TOTP_HASH_ALGORITHM = "sha1"  # HMAC-SHA1 per RFC 6238


def generate_totp_secret() -> str:
    """Generate a 20-byte base32-encoded TOTP secret.

    Returns a base32 string suitable for use with authenticator apps.
    """
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _hotp(key: bytes, counter: int) -> str:
    """Compute HOTP (RFC 4226) for the given counter.

    Uses HMAC-SHA1 and returns a 6-digit zero-padded string.
    """
    counter_bytes = counter.to_bytes(8, byteorder="big")
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = (
        (digest[offset] & 0x7F) << 24
        | (digest[offset + 1] & 0xFF) << 16
        | (digest[offset + 2] & 0xFF) << 8
        | (digest[offset + 3] & 0xFF)
    )
    code = binary % (10**TOTP_DIGITS)
    return str(code).zfill(TOTP_DIGITS)


def _secret_to_key(secret: str) -> bytes:
    """Convert a base32 secret string to raw key bytes.

    Handles missing padding by re-padding to the next multiple of 8.
    """
    padded = secret + "=" * (-len(secret) % 8)
    return base64.b32decode(padded, casefold=True)


def get_current_totp_code(secret: str, timestamp: int | None = None) -> str:
    """Return the current 6-digit TOTP code for *secret*.

    Primarily for testing; in production use :func:`verify_totp`.
    """
    if timestamp is None:
        timestamp = int(time.time())
    key = _secret_to_key(secret)
    counter = timestamp // TOTP_TIME_STEP
    return _hotp(key, counter)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """Verify a TOTP code against *secret* with a ±window tolerance.

    *window* specifies the number of 30-second steps to check
    before and after the current time. A window of 1 checks
    -1, 0, and +1 steps (±30 seconds).
    """
    key = _secret_to_key(secret)
    timestamp = int(time.time())
    counter = timestamp // TOTP_TIME_STEP
    for offset in range(-window, window + 1):
        expected = _hotp(key, counter + offset)
        if hmac.compare_digest(expected, code):
            return True
    return False


def generate_totp_provisioning_uri(
    email: str,
    secret: str,
    issuer: str = "Kian Trading Intelligence",
) -> str:
    """Generate an otpauth:// provisioning URI for authenticator apps.

    Format: ``otpauth://totp/<issuer>:<email>?secret=...&issuer=...``
    """
    label = f"{issuer}:{email}"
    params = {
        "secret": secret,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": str(TOTP_DIGITS),
        "period": str(TOTP_TIME_STEP),
    }
    return f"otpauth://totp/{quote(label)}?{urlencode(params)}"
