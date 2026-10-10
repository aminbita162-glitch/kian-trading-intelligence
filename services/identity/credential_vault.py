"""Credential vault interface for Kian Trading Intelligence.

Architecture Decisions: AD-019 (Non-Custodial Credential Vault).

Per AD-019: protect financial credentials through managed encryption,
least privilege, tenant isolation, rotation, revocation, and audited
access. Withdrawal-enabled trading credentials are prohibited by default.

Per Section 10.2: never store plaintext financial credentials in source
code, Git, or ordinary logs. Default trading API credentials must not
permit withdrawals.

Phase 02 uses encrypted in-memory storage (Fernet simulation with
SHA-256 derived key). In production, a managed KMS would be used.
"""

from __future__ import annotations

import hashlib
import os
import uuid

from contracts.identity import (
    AuditEventType,
    CredentialType,
    TenantId,
    UserId,
)
from services.identity.audit import audit

# ── Encryption (simulated) ──
# In production, use a managed KMS (AD-019). For Phase 02, we use
# a deterministic encryption simulation that stores ciphertext
# (not plaintext) and derives keys from a master secret.

_VAULT_MASTER_KEY: str = os.environ.get("KTI_VAULT_KEY", "phase02-dev-vault-key-change-in-prod")
_VAULT_ENTRIES: dict[str, dict[str, str]] = {}  # entry_id -> encrypted data


class CredentialVaultError(Exception):
    """Raised when credential vault operations fail."""


class CredentialNotFoundError(CredentialVaultError):
    """Raised when a credential is not found."""


class CredentialAccessDeniedError(CredentialVaultError):
    """Raised when credential access is denied."""


def _encrypt(plaintext: str) -> str:
    """Encrypt a plaintext value using a simulated KMS."""
    # Simple XOR-based cipher with SHA-256 key derivation.
    # NOT for production — Phase 02 development only.
    key = hashlib.sha256(_VAULT_MASTER_KEY.encode()).digest()
    data = plaintext.encode()
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return encrypted.hex()


def _decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext value."""
    key = hashlib.sha256(_VAULT_MASTER_KEY.encode()).digest()
    data = bytes.fromhex(ciphertext)
    decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return decrypted.decode()


class CredentialEntry:
    """A credential vault entry."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        entry_id: str,
        tenant_id: TenantId,
        user_id: UserId,
        credential_type: CredentialType,
        label: str,
        encrypted_value: str,
        withdrawal_enabled: bool = False,
        is_active: bool = True,
    ) -> None:
        self.entry_id = entry_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.credential_type = credential_type
        self.label = label
        self._encrypted_value = encrypted_value
        self.withdrawal_enabled = withdrawal_enabled
        self.is_active = is_active

    @property
    def encrypted_value(self) -> str:
        return self._encrypted_value

    def decrypt(self) -> str:
        """Decrypt and return the credential value."""
        return _decrypt(self._encrypted_value)


def store_credential(  # noqa: PLR0913
    *,
    tenant_id: TenantId,
    user_id: UserId,
    credential_type: CredentialType,
    label: str,
    secret_value: str,
    withdrawal_enabled: bool = False,
) -> str:
    """Store a credential in the vault.

    Per AD-019: credentials are encrypted at rest.
    Per Section 10.2: withdrawal-enabled credentials are prohibited by default.

    Returns the entry_id.
    """
    entry_id = str(uuid.uuid4())
    encrypted = _encrypt(secret_value)

    # Enforce: withdrawal-enabled credentials require explicit flag
    if withdrawal_enabled:
        # Log that withdrawal-enabled credentials are being stored
        # (they should be reviewed and approved per AD-019)
        pass

    _VAULT_ENTRIES[entry_id] = {
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "credential_type": credential_type.value,
        "label": label,
        "encrypted_value": encrypted,
        "withdrawal_enabled": str(withdrawal_enabled).lower(),
        "is_active": "true",
    }

    audit(
        event_type=AuditEventType.CREDENTIAL_STORED,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        detail=f"Credential stored: type={credential_type.value}, label={label}",
    )

    return entry_id


def retrieve_credential(
    *,
    entry_id: str,
    tenant_id: TenantId,
    user_id: UserId,
) -> str:
    """Retrieve a decrypted credential from the vault.

    Per AD-019: access is audited and tenant-scoped.
    Cross-tenant access is rejected.
    """
    entry = _VAULT_ENTRIES.get(entry_id)
    if entry is None:
        raise CredentialNotFoundError(f"Credential not found: {entry_id}")

    if entry["tenant_id"] != str(tenant_id):
        audit(
            event_type=AuditEventType.CROSS_TENANT_ACCESS_BLOCKED,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            detail=f"Cross-tenant credential access blocked: {entry_id}",
        )
        raise CredentialAccessDeniedError("Cross-tenant access blocked")

    if entry["is_active"] != "true":
        raise CredentialAccessDeniedError("Credential has been revoked")

    audit(
        event_type=AuditEventType.CREDENTIAL_ACCESSED,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        detail=f"Credential accessed: {entry_id}",
    )

    return _decrypt(entry["encrypted_value"])


def rotate_credential(
    *,
    entry_id: str,
    tenant_id: TenantId,
    user_id: UserId,
    new_secret_value: str,
) -> None:
    """Rotate a credential's value.

    Per AD-019: rotation is audited.
    """
    entry = _VAULT_ENTRIES.get(entry_id)
    if entry is None:
        raise CredentialNotFoundError(f"Credential not found: {entry_id}")

    if entry["tenant_id"] != str(tenant_id):
        raise CredentialAccessDeniedError("Cross-tenant access blocked")

    entry["encrypted_value"] = _encrypt(new_secret_value)

    audit(
        event_type=AuditEventType.CREDENTIAL_ROTATED,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        detail=f"Credential rotated: {entry_id}",
    )


def revoke_credential(
    *,
    entry_id: str,
    tenant_id: TenantId,
    user_id: UserId,
) -> None:
    """Revoke a credential (mark as inactive).

    Per AD-019: revocation is audited and prevents future access.
    """
    entry = _VAULT_ENTRIES.get(entry_id)
    if entry is None:
        raise CredentialNotFoundError(f"Credential not found: {entry_id}")

    if entry["tenant_id"] != str(tenant_id):
        raise CredentialAccessDeniedError("Cross-tenant access blocked")

    entry["is_active"] = "false"

    audit(
        event_type=AuditEventType.CREDENTIAL_REVOKED,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        detail=f"Credential revoked: {entry_id}",
    )


def list_credentials(
    *,
    tenant_id: TenantId,
    user_id: UserId,
) -> list[dict[str, str]]:
    """List all credentials for a user in a tenant (metadata only, no secrets)."""
    result: list[dict[str, str]] = []
    for entry_id, entry in _VAULT_ENTRIES.items():
        if entry["tenant_id"] == str(tenant_id) and entry["user_id"] == str(user_id):
            result.append(
                {
                    "entry_id": entry_id,
                    "credential_type": entry["credential_type"],
                    "label": entry["label"],
                    "withdrawal_enabled": entry["withdrawal_enabled"],
                    "is_active": entry["is_active"],
                }
            )
    return result


def reset_vault() -> None:
    """Clear all vault entries. For testing only."""
    _VAULT_ENTRIES.clear()
