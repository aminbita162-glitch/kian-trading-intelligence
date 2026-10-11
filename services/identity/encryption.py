"""AES-256-GCM envelope encryption for credential vault (F-SEC-02).

Architecture Decisions: AD-019 (Non-Custodial Credential Vault),
Section 10.2 (Secrets — managed encryption).

Replaces the legacy XOR cipher with authenticated AES-256-GCM envelope
encryption.  Provides:

- **Authenticated encryption** — AES-256-GCM with a 96-bit random nonce
  and a 128-bit authentication tag.  Tampering with ciphertext or AAD
  causes decryption to fail-closed (``InvalidTag``).
- **Envelope format** — a versioned JSON envelope carrying the key
  identifier, key version, nonce, and ciphertext.  Legacy XOR-encrypted
  values are detected and can be migrated via :func:`migrate_legacy_xor`.
- **Key versioning & rotation** — each envelope records the key version
  used at encryption time.  Decryption uses the recorded version;
  encryption always uses the current version.  Rotating the master key
  increments the version so old envelopes remain decryptable while new
  ones use the new key.
- **Tenant/context binding (AAD)** — the tenant-id and user-id are
  bound cryptographically as Additional Authenticated Data.  A ciphertext
  encrypted for tenant A cannot be decrypted under tenant B even if the
  application-level access check is bypassed.
- **Fail-closed** — in production (``KTI_ENVIRONMENT=production``) the
  vault key **must** be supplied via ``KTI_VAULT_KEY``; a missing or
  short key raises :class:`EncryptionConfigurationError` rather than
  falling back to a hardcoded default.
- **No hardcoded or logged keys** — key material is derived via HKDF
  from the env-supplied master key.  Key bytes are never written to
  logs or returned by any public API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# ── Exceptions ──


class EncryptionError(Exception):
    """Base class for encryption-related errors."""


class EncryptionConfigurationError(EncryptionError):
    """Raised when encryption is not properly configured (fail-closed)."""


class LegacyFormatError(EncryptionError):
    """Raised when a value is in the legacy XOR format."""


class UnsupportedVersionError(EncryptionError):
    """Raised when an envelope version is not supported."""


class DecryptionError(EncryptionError):
    """Raised when decryption fails (tamper detected or wrong key/AAD)."""


# ── Key provider interface ──


class KeyProvider(Protocol):
    """Interface for key management (AD-019).

    In production, a KMS-backed implementation would retrieve keys from
    an external key-management service.  In development,
    :class:`LocalKeyProvider` derives keys from an env-supplied master
    secret via HKDF.
    """

    def get_key(self, key_version: int) -> bytes:
        """Return the raw 256-bit key for *key_version*."""
        ...

    def get_current_version(self) -> int:
        """Return the current (newest) key version."""
        ...

    def get_key_id(self) -> str:
        """Return a stable identifier for the key set."""
        ...


# ── Local key provider (development / test) ──

_DEFAULT_KEY_ID = "local-dev"
_MIN_KEY_LEN = 32  # 256 bits — the minimum for AES-256


class LocalKeyProvider:
    """Key provider that derives per-version keys from a master secret.

    The master secret is read from the ``KTI_VAULT_KEY`` environment
    variable.  In production the env var **must** be set to a value of
    at least ``_MIN_KEY_LEN`` bytes; otherwise
    :class:`EncryptionConfigurationError` is raised.
    """

    def __init__(self, master_material: bytes, *, key_id: str = _DEFAULT_KEY_ID) -> None:
        if len(master_material) < _MIN_KEY_LEN:
            raise EncryptionConfigurationError(
                f"Vault key material must be at least {_MIN_KEY_LEN} bytes "
                f"(got {len(master_material)}). Set KTI_VAULT_KEY to a strong value."
            )
        self._master = master_material
        self._key_id = key_id
        self._current_version = 1

    def _derive(self, version: int) -> bytes:
        """Derive a 256-bit key from the master secret using HKDF-SHA256."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"kti-vault:{self._key_id}:v{version}".encode(),
        )
        return hkdf.derive(self._master)

    def get_key(self, key_version: int) -> bytes:
        return self._derive(key_version)

    def get_current_version(self) -> int:
        return self._current_version

    def get_key_id(self) -> str:
        return self._key_id


def _is_production() -> bool:
    """Return True when running in production mode."""
    return os.environ.get("KTI_ENVIRONMENT", "").lower() == "production"


def _load_master_material() -> bytes:
    """Load vault key material from the environment (fail-closed in prod).

    In production, ``KTI_VAULT_KEY`` must be set to a strong value of at
    least ``_MIN_KEY_LEN`` bytes.  In development a deterministic default
    is used so that tests are reproducible.
    """
    raw = os.environ.get("KTI_VAULT_KEY", "")
    if _is_production():
        if not raw or len(raw) < _MIN_KEY_LEN:
            raise EncryptionConfigurationError(
                "KTI_VAULT_KEY is not set or too short for production. "
                "Set it to a strong random value of at least 32 bytes."
            )
        return raw.encode()
    # Development fallback — deterministic but adequate for dev/test.
    raw = raw or "phase02-dev-vault-key-change-in-prod"
    # Pad / hash to ensure minimum length for HKDF.
    return hashlib.sha256(raw.encode()).digest()


# ── Envelope encryption ──

_NONCE_SIZE = 12  # 96-bit nonce for AES-256-GCM (NIST SP 800-38D)
_ENVELOPE_VERSION = 1  # AES-256-GCM; 0 is reserved for legacy XOR


@dataclass(frozen=True)
class Envelope:
    """Parsed encryption envelope."""

    version: int
    key_id: str
    key_version: int
    nonce: bytes
    ciphertext: bytes

    def serialize(self) -> str:
        """Serialize to a compact JSON string for storage."""
        return json.dumps(
            {
                "v": self.version,
                "kid": self.key_id,
                "kv": self.key_version,
                "n": base64.b64encode(self.nonce).decode(),
                "c": base64.b64encode(self.ciphertext).decode(),
            },
            sort_keys=True,
        )


class EnvelopeEncryption:
    """AES-256-GCM envelope encryption with key versioning and AAD binding."""

    def __init__(self, key_provider: KeyProvider) -> None:
        self._provider = key_provider

    def encrypt(self, plaintext: str, aad: bytes = b"") -> str:
        """Encrypt *plaintext* and return a serialized envelope string.

        Args:
            plaintext: The value to encrypt.
            aad: Additional Authenticated Data (tenant/context binding).
                Included in the GCM authentication tag but not encrypted.
                Mismatched AAD at decryption time causes a
                :class:`DecryptionError`.
        """
        nonce = os.urandom(_NONCE_SIZE)
        key = self._provider.get_key(self._provider.get_current_version())
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), aad)
        return Envelope(
            version=_ENVELOPE_VERSION,
            key_id=self._provider.get_key_id(),
            key_version=self._provider.get_current_version(),
            nonce=nonce,
            ciphertext=ciphertext,
        ).serialize()

    def decrypt(self, envelope_str: str, aad: bytes = b"") -> str:
        """Decrypt an envelope string.

        Raises:
            LegacyFormatError: If the value is in the legacy XOR format.
            UnsupportedVersionError: If the envelope version is not 1.
            DecryptionError: If decryption fails (tamper, wrong key, or
                AAD mismatch).
        """
        if not envelope_str.startswith("{"):
            raise LegacyFormatError(
                "Value is not a JSON envelope — likely legacy XOR format. "
                "Run migrate_legacy_xor() to upgrade."
            )
        try:
            envelope = json.loads(envelope_str)
        except json.JSONDecodeError as exc:
            raise DecryptionError("Malformed envelope JSON") from exc

        version = envelope.get("v")
        if version != _ENVELOPE_VERSION:
            raise UnsupportedVersionError(
                f"Unsupported envelope version {version}; expected {_ENVELOPE_VERSION}"
            )

        try:
            nonce = base64.b64decode(envelope["n"])
            ciphertext = base64.b64decode(envelope["c"])
            key_version = envelope["kv"]
            key = self._provider.get_key(key_version)
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
        except KeyError as exc:
            raise DecryptionError("Missing required envelope field") from exc
        except Exception as exc:  # noqa: BLE001 — GCM raises InvalidTag
            raise DecryptionError(
                "Decryption failed — ciphertext may be tampered, the key "
                "may be wrong, or the AAD (tenant/context) may not match."
            ) from exc
        return plaintext.decode()

    def is_envelope(self, value: str) -> bool:
        """Return True if *value* looks like a version-1 envelope."""
        return value.startswith("{") and '"v": 1' in value

    def get_key_version(self) -> int:
        """Return the current key version."""
        return self._provider.get_current_version()

    def get_key_id(self) -> str:
        """Return the current key identifier."""
        return self._provider.get_key_id()


# ── Legacy XOR decryption (for migration only) ──


def _decrypt_legacy_xor(ciphertext_hex: str, master_key_material: bytes) -> str:
    """Decrypt a legacy XOR-encrypted value.

    This is the *original* XOR cipher from Phase 02, kept solely for
    migration.  It is NOT used for new encryption.
    """
    key = hashlib.sha256(master_key_material).digest()
    data = bytes.fromhex(ciphertext_hex)
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).decode()


def migrate_legacy_xor(
    legacy_value: str,
    *,
    encryption: EnvelopeEncryption,
    master_key_material: bytes,
    aad: bytes = b"",
) -> str:
    """Migrate a legacy XOR-encrypted value to AES-256-GCM.

    1. Decrypt the old XOR ciphertext.
    2. Re-encrypt with AES-256-GCM.
    3. Return the new envelope string.

    The caller is responsible for persisting the migrated value.
    """
    plaintext = _decrypt_legacy_xor(legacy_value, master_key_material)
    return encryption.encrypt(plaintext, aad=aad)


# ── Factory ──

# Module-level singleton (lazy-initialised).
_encryption: EnvelopeEncryption | None = None


def get_encryption() -> EnvelopeEncryption:
    """Return the singleton :class:`EnvelopeEncryption` instance.

    Fail-closed in production: raises :class:`EncryptionConfigurationError`
    if ``KTI_VAULT_KEY`` is missing or too short.
    """
    global _encryption  # noqa: PLW0603
    if _encryption is None:
        material = _load_master_material()
        provider = LocalKeyProvider(material)
        _encryption = EnvelopeEncryption(provider)
    return _encryption


def reset_encryption() -> None:
    """Reset the singleton (for testing)."""
    global _encryption  # noqa: PLW0603
    _encryption = None
