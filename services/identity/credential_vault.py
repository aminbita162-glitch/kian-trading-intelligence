"""Credential vault interface for Kian Trading Intelligence.

Architecture Decisions: AD-019 (Non-Custodial Credential Vault).

Per AD-019: protect financial credentials through managed encryption,
least privilege, tenant isolation, rotation, revocation, and audited
access. Withdrawal-enabled trading credentials are prohibited by default.

Per Section 10.2: never store plaintext financial credentials in source
code, Git, or ordinary logs. Default trading API credentials must not
permit withdrawals.

F-SEC-02 RESOLVED: Replaced legacy XOR cipher with AES-256-GCM
envelope encryption with key versioning, tenant/context binding (AAD),
and fail-closed behavior. Legacy XOR-encrypted values can be migrated
via :func:`migrate_all_legacy`.
"""

from __future__ import annotations

import uuid

from contracts.identity import (
    AuditEventType,
    CredentialType,
    TenantId,
    UserId,
)
from services.identity.audit import audit
from services.identity.encryption import (
    EnvelopeEncryption,
    get_encryption,
    migrate_legacy_xor,
    reset_encryption,
)

# ── Exceptions ──


class CredentialVaultError(Exception):
    """Raised when credential vault operations fail."""


class CredentialNotFoundError(CredentialVaultError):
    """Raised when a credential is not found."""


class CredentialAccessDeniedError(CredentialVaultError):
    """Raised when credential access is denied."""


class CredentialDecryptionError(CredentialVaultError):
    """Raised when credential decryption fails (tamper or wrong context)."""


# ── In-memory credential metadata store ──
# The encrypted value is stored as an AES-256-GCM envelope string.
# The vault holds only metadata + the envelope ciphertext.

_VAULT_ENTRIES: dict[str, dict[str, str]] = {}  # entry_id -> encrypted data


def _build_aad(tenant_id: TenantId, user_id: UserId) -> bytes:
    """Build Additional Authenticated Data for tenant/context binding.

    The AAD binds the ciphertext to the tenant and user so that a
    credential encrypted for tenant A cannot be decrypted under
    tenant B even if the access check is bypassed.
    """
    return f"tenant:{tenant_id}|user:{user_id}".encode()


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
        enc = get_encryption()
        aad = _build_aad(self.tenant_id, self.user_id)
        return enc.decrypt(self._encrypted_value, aad=aad)


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

    Per AD-019: credentials are encrypted at rest with AES-256-GCM.
    Per Section 10.2: withdrawal-enabled credentials are prohibited by default.

    Returns the entry_id.
    """
    entry_id = str(uuid.uuid4())
    enc = get_encryption()
    aad = _build_aad(tenant_id, user_id)
    encrypted = enc.encrypt(secret_value, aad=aad)

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

    enc = get_encryption()
    aad = _build_aad(tenant_id, user_id)
    try:
        return enc.decrypt(entry["encrypted_value"], aad=aad)
    except Exception as exc:  # noqa: BLE001
        raise CredentialDecryptionError(
            "Credential decryption failed — possible tamper or context mismatch"
        ) from exc


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

    enc = get_encryption()
    aad = _build_aad(tenant_id, user_id)
    entry["encrypted_value"] = enc.encrypt(new_secret_value, aad=aad)

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
    """Clear all vault entries and reset encryption (for testing)."""
    _VAULT_ENTRIES.clear()
    reset_encryption()


def migrate_all_legacy(
    *,
    master_key_material: bytes,
    encryption: EnvelopeEncryption | None = None,
) -> int:
    """Migrate all legacy XOR-encrypted credentials to AES-256-GCM.

    Returns the number of migrated entries.
    """
    enc = encryption or get_encryption()
    migrated = 0
    for _entry_id, entry in list(_VAULT_ENTRIES.items()):
        val = entry["encrypted_value"]
        # Legacy XOR values are hex strings (not JSON envelopes).
        if val.startswith("{"):
            continue  # Already migrated
        try:
            tenant_id = TenantId.__new__(TenantId)
            object.__setattr__(tenant_id, "value", uuid.UUID(entry["tenant_id"]))
            user_id = UserId.__new__(UserId)
            object.__setattr__(user_id, "value", uuid.UUID(entry["user_id"]))
            aad = _build_aad(tenant_id, user_id)
            new_val = migrate_legacy_xor(
                val,
                encryption=enc,
                master_key_material=master_key_material,
                aad=aad,
            )
            entry["encrypted_value"] = new_val
            migrated += 1
        except Exception:  # noqa: BLE001
            # Skip entries that fail migration — don't corrupt them.
            pass
    return migrated
