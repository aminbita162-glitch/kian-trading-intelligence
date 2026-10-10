"""Adversarial credential vault tests for Phase 02.

Architecture Decisions: AD-019 (Non-Custodial Credential Vault),
Section 10.2 (Secrets).

Tests: credential storage, retrieval, rotation, revocation,
cross-tenant access rejection, and plaintext-never-stored verification.
"""

from __future__ import annotations

import uuid

import pytest

from contracts.identity import CredentialType, TenantId, UserId, UserRole
from services.identity.auth import register_user
from services.identity.credential_vault import (
    _VAULT_ENTRIES,
    CredentialAccessDeniedError,
    CredentialNotFoundError,
    list_credentials,
    retrieve_credential,
    revoke_credential,
    rotate_credential,
    store_credential,
)
from services.identity.tenant import create_tenant


class TestCredentialVault:
    def _setup(self) -> tuple[TenantId, UserId]:
        """Create a tenant and user for testing."""
        tenant = create_tenant(name="Vault Test Tenant")
        user = register_user(
            tenant_id=tenant.tenant_id,
            email="vault@test.com",
            password="test-password-123",
            role=UserRole.ADMIN.value,
        )
        return tenant.tenant_id, user.user_id

    def test_store_and_retrieve_credential(self) -> None:
        """Stored credential can be retrieved and decrypted."""
        tenant_id, user_id = self._setup()
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Binance API Key",
            secret_value="my-secret-api-key-value-12345",
        )
        retrieved = retrieve_credential(
            entry_id=entry_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        assert retrieved == "my-secret-api-key-value-12345"

    def test_credential_not_stored_in_plaintext(self) -> None:
        """Credential vault does not store plaintext values."""
        tenant_id, user_id = self._setup()
        secret_value = "plaintext-must-not-appear-in-storage-xyz"
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_SECRET,
            label="Test Secret",
            secret_value=secret_value,
        )
        # Check the internal storage does not contain plaintext
        stored = _VAULT_ENTRIES[entry_id]["encrypted_value"]
        assert secret_value not in stored
        # Decryption should work
        decrypted = retrieve_credential(
            entry_id=entry_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        assert decrypted == secret_value

    def test_cross_tenant_credential_access_blocked(self) -> None:
        """Cross-tenant credential access is rejected."""
        tenant_a_id, user_a_id = self._setup()
        # Create tenant B
        tenant_b = create_tenant(name="Tenant B")
        user_b = register_user(
            tenant_id=tenant_b.tenant_id,
            email="vault-b@test.com",
            password="test-password-123",
            role=UserRole.ADMIN.value,
        )
        entry_id = store_credential(
            tenant_id=tenant_a_id,
            user_id=user_a_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Tenant A Key",
            secret_value="tenant-a-secret-key-value-12345",
        )
        # User from tenant B tries to access
        with pytest.raises(CredentialAccessDeniedError):
            retrieve_credential(
                entry_id=entry_id,
                tenant_id=tenant_b.tenant_id,
                user_id=user_b.user_id,
            )

    def test_credential_not_found(self) -> None:
        """Non-existent credential raises CredentialNotFoundError."""
        tenant_id, user_id = self._setup()
        with pytest.raises(CredentialNotFoundError):
            retrieve_credential(
                entry_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
            )

    def test_rotate_credential(self) -> None:
        """Credential rotation updates the encrypted value."""
        tenant_id, user_id = self._setup()
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Rotatable Key",
            secret_value="original-secret-value-12345",
        )
        rotate_credential(
            entry_id=entry_id,
            tenant_id=tenant_id,
            user_id=user_id,
            new_secret_value="rotated-secret-value-67890",
        )
        retrieved = retrieve_credential(
            entry_id=entry_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        assert retrieved == "rotated-secret-value-67890"

    def test_revoke_credential(self) -> None:
        """Revoked credentials cannot be retrieved."""
        tenant_id, user_id = self._setup()
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Revocable Key",
            secret_value="to-be-revoked-12345",
        )
        revoke_credential(
            entry_id=entry_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        with pytest.raises(CredentialAccessDeniedError):
            retrieve_credential(
                entry_id=entry_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )

    def test_list_credentials(self) -> None:
        """list_credentials returns metadata without secrets."""
        tenant_id, user_id = self._setup()
        store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Key 1",
            secret_value="secret-value-one-12345",
        )
        store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_SECRET,
            label="Key 2",
            secret_value="secret-value-two-12345",
        )
        creds = list_credentials(tenant_id=tenant_id, user_id=user_id)
        assert len(creds) == 2
        # Verify no secret values in the listing
        for cred in creds:
            assert "secret_value" not in cred
            assert "encrypted_value" not in cred
            assert "label" in cred
            assert "entry_id" in cred

    def test_cross_tenant_rotation_blocked(self) -> None:
        """Cross-tenant credential rotation is rejected."""
        tenant_a_id, user_a_id = self._setup()
        tenant_b = create_tenant(name="Tenant B")
        user_b = register_user(
            tenant_id=tenant_b.tenant_id,
            email="vault-b@test.com",
            password="test-password-123",
            role=UserRole.ADMIN.value,
        )
        entry_id = store_credential(
            tenant_id=tenant_a_id,
            user_id=user_a_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Tenant A Key",
            secret_value="tenant-a-secret-12345",
        )
        with pytest.raises(CredentialAccessDeniedError):
            rotate_credential(
                entry_id=entry_id,
                tenant_id=tenant_b.tenant_id,
                user_id=user_b.user_id,
                new_secret_value="hijacked-value-67890",
            )

    def test_cross_tenant_revocation_blocked(self) -> None:
        """Cross-tenant credential revocation is rejected."""
        tenant_a_id, user_a_id = self._setup()
        tenant_b = create_tenant(name="Tenant B")
        user_b = register_user(
            tenant_id=tenant_b.tenant_id,
            email="vault-b@test.com",
            password="test-password-123",
            role=UserRole.ADMIN.value,
        )
        entry_id = store_credential(
            tenant_id=tenant_a_id,
            user_id=user_a_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Tenant A Key",
            secret_value="tenant-a-secret-12345",
        )
        with pytest.raises(CredentialAccessDeniedError):
            revoke_credential(
                entry_id=entry_id,
                tenant_id=tenant_b.tenant_id,
                user_id=user_b.user_id,
            )

    def test_withdrawal_disabled_by_default(self) -> None:
        """Credentials are stored with withdrawal_enabled=False by default."""
        tenant_id, user_id = self._setup()
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Default Key",
            secret_value="no-withdrawal-key-12345",
        )
        creds = list_credentials(tenant_id=tenant_id, user_id=user_id)
        cred = next(c for c in creds if c["entry_id"] == entry_id)
        assert cred["withdrawal_enabled"] == "false"
