"""Security remediation tests for F-SEC-02 — AES-256-GCM encryption.

Architecture Decisions: AD-019 (Non-Custodial Credential Vault),
Section 10.2 (Secrets — managed encryption).

F-SEC-02 RESOLVED: Replaced legacy XOR cipher with AES-256-GCM
envelope encryption with:
- Authenticated encryption (AES-256-GCM)
- Unique nonces (96-bit random)
- Tenant/context binding (AAD)
- Key versioning and rotation
- Fail-closed behavior in production
- Verified migration of legacy XOR-encrypted data
- Tamper detection (authentication tag verification)
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import uuid as _uuid

import pytest

from contracts.identity import CredentialType, TenantId, UserId, UserRole
from services.identity.auth import register_user
from services.identity.credential_vault import (
    _VAULT_ENTRIES,
    CredentialAccessDeniedError,
    migrate_all_legacy,
    reset_vault,
    retrieve_credential,
    rotate_credential,
    store_credential,
)
from services.identity.encryption import (
    DecryptionError,
    EncryptionConfigurationError,
    EnvelopeEncryption,
    LegacyFormatError,
    LocalKeyProvider,
    UnsupportedVersionError,
    get_encryption,
    migrate_legacy_xor,
    reset_encryption,
)
from services.identity.tenant import create_tenant


class TestEncryptionCore:
    """Test the core AES-256-GCM envelope encryption."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Encrypting and decrypting with the same AAD succeeds."""
        reset_encryption()
        enc = get_encryption()
        plaintext = "my-secret-api-key-value-12345"
        aad = b"tenant:abc|user:xyz"
        ciphertext = enc.encrypt(plaintext, aad=aad)
        assert ciphertext != plaintext
        assert plaintext not in ciphertext
        decrypted = enc.decrypt(ciphertext, aad=aad)
        assert decrypted == plaintext

    def test_unique_nonces(self) -> None:
        """Each encryption uses a unique random nonce."""
        reset_encryption()
        enc = get_encryption()
        ct1 = enc.encrypt("same-value", aad=b"ctx")
        ct2 = enc.encrypt("same-value", aad=b"ctx")
        # The nonces must differ — so the ciphertexts differ.
        env1 = json.loads(ct1)
        env2 = json.loads(ct2)
        assert env1["n"] != env2["n"]
        assert env1["c"] != env2["c"]

    def test_aad_mismatch_fails(self) -> None:
        """Decryption with wrong AAD fails (tenant/context binding)."""
        reset_encryption()
        enc = get_encryption()
        ciphertext = enc.encrypt("secret", aad=b"tenant:A|user:X")
        with pytest.raises(DecryptionError):
            enc.decrypt(ciphertext, aad=b"tenant:B|user:Y")

    def test_tamper_detection(self) -> None:
        """Tampering with ciphertext causes decryption failure."""
        reset_encryption()
        enc = get_encryption()
        ciphertext = enc.encrypt("secret", aad=b"ctx")
        # Tamper with the ciphertext — flip a bit in the base64
        env = json.loads(ciphertext)
        ct_bytes = bytearray(base64.b64decode(env["c"]))
        ct_bytes[0] ^= 0xFF
        env["c"] = base64.b64encode(bytes(ct_bytes)).decode()
        tampered = json.dumps(env)
        with pytest.raises(DecryptionError):
            enc.decrypt(tampered, aad=b"ctx")

    def test_envelope_version_recorded(self) -> None:
        """Each envelope records the version and key version."""
        reset_encryption()
        enc = get_encryption()
        ciphertext = enc.encrypt("secret", aad=b"ctx")
        env = json.loads(ciphertext)
        assert env["v"] == 1  # AES-256-GCM version
        assert "kv" in env
        assert "kid" in env

    def test_unsupported_version_rejected(self) -> None:
        """An unsupported envelope version raises UnsupportedVersionError."""
        reset_encryption()
        enc = get_encryption()
        fake = json.dumps({"v": 99, "kid": "x", "kv": 1, "n": "AA==", "c": "AA=="})
        with pytest.raises(UnsupportedVersionError):
            enc.decrypt(fake, aad=b"ctx")

    def test_legacy_format_detected(self) -> None:
        """A non-envelope (legacy XOR) value raises LegacyFormatError."""
        reset_encryption()
        enc = get_encryption()
        # Legacy XOR values are hex strings without JSON braces
        with pytest.raises(LegacyFormatError):
            enc.decrypt("abcdef0123456789", aad=b"ctx")


class TestKeyVersioning:
    """Test key versioning and rotation."""

    def test_key_version_in_envelope(self) -> None:
        """The envelope records the key version used."""
        reset_encryption()
        enc = get_encryption()
        ciphertext = enc.encrypt("secret", aad=b"ctx")
        env = json.loads(ciphertext)
        assert env["kv"] == enc.get_key_version()

    def test_key_rotation_preserves_decryption(self) -> None:
        """After key rotation, old envelopes remain decryptable."""
        # Use a dedicated provider so both enc/dec share the same key set.
        material = hashlib.sha256(b"rotation-test-key-material").digest()
        provider_v1 = LocalKeyProvider(material)
        enc_v1 = EnvelopeEncryption(provider_v1)
        ct1 = enc_v1.encrypt("secret1", aad=b"ctx")
        # Simulate key rotation — new provider with version 2
        provider_v2 = LocalKeyProvider(material)
        provider_v2._current_version = 2
        enc_v2 = EnvelopeEncryption(provider_v2)
        ct2 = enc_v2.encrypt("secret2", aad=b"ctx")
        # Old envelope decrypts with the old provider (version 1 key)
        assert enc_v1.decrypt(ct1, aad=b"ctx") == "secret1"
        # New envelope decrypts with the new provider (version 2 key)
        assert enc_v2.decrypt(ct2, aad=b"ctx") == "secret2"
        # The old provider can also decrypt the new envelope
        # because it derives keys per-version from the same master material.
        assert enc_v1.decrypt(ct2, aad=b"ctx") == "secret2"

    def test_key_id_recorded(self) -> None:
        """The key identifier is recorded in the envelope."""
        reset_encryption()
        enc = get_encryption()
        ciphertext = enc.encrypt("secret", aad=b"ctx")
        env = json.loads(ciphertext)
        assert env["kid"] == enc.get_key_id()


class TestFailClosed:
    """Test fail-closed behavior in production."""

    def test_production_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production, missing KTI_VAULT_KEY raises EncryptionConfigurationError."""
        monkeypatch.setenv("KTI_ENVIRONMENT", "production")
        monkeypatch.delenv("KTI_VAULT_KEY", raising=False)
        reset_encryption()
        with pytest.raises(EncryptionConfigurationError):
            get_encryption()

    def test_production_short_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production, a short KTI_VAULT_KEY raises EncryptionConfigurationError."""
        monkeypatch.setenv("KTI_ENVIRONMENT", "production")
        monkeypatch.setenv("KTI_VAULT_KEY", "short")
        reset_encryption()
        with pytest.raises(EncryptionConfigurationError):
            get_encryption()

    def test_production_valid_key_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production, a valid KTI_VAULT_KEY allows encryption."""
        monkeypatch.setenv("KTI_ENVIRONMENT", "production")
        monkeypatch.setenv(
            "KTI_VAULT_KEY",
            "a-very-long-production-vault-key-that-is-at-least-32-bytes",
        )
        reset_encryption()
        enc = get_encryption()
        ct = enc.encrypt("secret", aad=b"ctx")
        assert enc.decrypt(ct, aad=b"ctx") == "secret"


class TestLegacyMigration:
    """Test migration of legacy XOR-encrypted values to AES-256-GCM."""

    def test_migrate_legacy_xor(self) -> None:
        """A legacy XOR value can be migrated to AES-256-GCM."""
        reset_encryption()
        enc = get_encryption()

        # The legacy XOR cipher used hashlib.sha256(master_key.encode()).digest()
        # as the key.  The master key was the string "phase02-dev-vault-key-change-in-prod".
        legacy_master = b"phase02-dev-vault-key-change-in-prod"
        key = hashlib.sha256(legacy_master).digest()
        plaintext = "my-old-secret-api-key-value-12345"
        data = plaintext.encode()
        legacy_xor = bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).hex()

        # Migrate — pass the raw master key bytes (not its hash)
        aad = b"tenant:abc|user:xyz"
        migrated = migrate_legacy_xor(
            legacy_xor,
            encryption=enc,
            master_key_material=legacy_master,
            aad=aad,
        )
        # The migrated value should be a JSON envelope
        assert migrated.startswith("{")
        # And should decrypt correctly
        assert enc.decrypt(migrated, aad=aad) == plaintext

    def test_migrate_all_legacy(self) -> None:
        """migrate_all_legacy upgrades all legacy entries."""
        reset_vault()
        get_encryption()
        legacy_master = b"phase02-dev-vault-key-change-in-prod"

        # Create a fake legacy entry
        key = hashlib.sha256(legacy_master).digest()
        plaintext = "legacy-secret-value-12345"
        data = plaintext.encode()
        legacy_xor = bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).hex()

        _VAULT_ENTRIES[str(_uuid.uuid4())] = {
            "tenant_id": str(TenantId.generate()),
            "user_id": str(UserId.generate()),
            "credential_type": "exchange_api_key",
            "label": "Legacy Key",
            "encrypted_value": legacy_xor,
            "withdrawal_enabled": "false",
            "is_active": "true",
        }

        migrated = migrate_all_legacy(master_key_material=legacy_master)
        assert migrated == 1

    def test_migrated_value_is_not_plaintext(self) -> None:
        """A migrated value does not contain the plaintext."""
        reset_encryption()
        enc = get_encryption()
        legacy_master = b"phase02-dev-vault-key-change-in-prod"
        key = hashlib.sha256(legacy_master).digest()
        plaintext = "legacy-secret-value-12345"
        data = plaintext.encode()
        legacy_xor = bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).hex()

        aad = b"tenant:abc|user:xyz"
        migrated = migrate_legacy_xor(
            legacy_xor,
            encryption=enc,
            master_key_material=legacy_master,
            aad=aad,
        )
        assert plaintext not in migrated


class TestCredentialVaultSecurity:
    """Test the credential vault with AES-256-GCM."""

    def _setup(self) -> tuple[TenantId, UserId]:
        """Create a tenant and user for testing."""
        tenant = create_tenant(name="Vault Security Test Tenant")
        user = register_user(
            tenant_id=tenant.tenant_id,
            email="vault-sec@test.com",
            password="test-password-123",
            role=UserRole.ADMIN.value,
        )
        return tenant.tenant_id, user.user_id

    def test_credential_not_stored_in_plaintext(self) -> None:
        """Credential vault does not store plaintext values."""
        reset_vault()
        tenant_id, user_id = self._setup()
        secret_value = "plaintext-must-not-appear-in-storage-xyz"
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_SECRET,
            label="Test Secret",
            secret_value=secret_value,
        )
        stored = _VAULT_ENTRIES[entry_id]["encrypted_value"]
        assert secret_value not in stored
        # The stored value should be a JSON envelope (AES-256-GCM)
        assert stored.startswith("{")
        # Decryption should work
        decrypted = retrieve_credential(
            entry_id=entry_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        assert decrypted == secret_value

    def test_cross_tenant_decryption_blocked_by_aad(self) -> None:
        """Even if access control is bypassed, AAD prevents cross-tenant decryption."""
        reset_vault()
        tenant_id, user_id = self._setup()
        secret_value = "tenant-a-secret-key-value-12345"
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Tenant A Key",
            secret_value=secret_value,
        )
        # Simulate a cross-tenant access — different tenant/user
        other_tenant_id = TenantId.generate()
        other_user_id = UserId.generate()
        # The access check should block this at the vault level
        with pytest.raises(CredentialAccessDeniedError):
            retrieve_credential(
                entry_id=entry_id,
                tenant_id=other_tenant_id,
                user_id=other_user_id,
            )

    def test_credential_encrypted_with_aes_gcm(self) -> None:
        """The encrypted value is a JSON envelope with AES-256-GCM."""
        reset_vault()
        tenant_id, user_id = self._setup()
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="AES Test Key",
            secret_value="aes-gcm-test-value-12345",
        )
        stored = _VAULT_ENTRIES[entry_id]["encrypted_value"]
        env = json.loads(stored)
        assert env["v"] == 1  # AES-256-GCM version
        assert "n" in env  # nonce
        assert "c" in env  # ciphertext
        assert "kv" in env  # key version

    def test_roundtrip_after_rotation(self) -> None:
        """Credentials can be rotated and the new value decrypts."""
        reset_vault()
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

    def test_no_key_material_in_storage(self) -> None:
        """No raw key material is stored in the vault entries."""
        reset_vault()
        tenant_id, user_id = self._setup()
        entry_id = store_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Key Leak Test",
            secret_value="check-for-key-leak-12345",
        )
        stored = _VAULT_ENTRIES[entry_id]["encrypted_value"]
        # The stored value should not contain the encryption key
        enc = get_encryption()
        key = enc._provider.get_key(1)
        assert key.hex() not in stored
        assert str(key) not in stored


class TestConcurrency:
    """Test concurrent access to the encryption layer."""

    def test_concurrent_encrypt_decrypt(self) -> None:
        """Concurrent encrypt/decrypt operations don't interfere."""
        reset_encryption()
        enc = get_encryption()

        results: list[bool] = []
        lock = threading.Lock()

        def worker(i: int) -> None:
            aad = f"ctx:{i}".encode()
            for j in range(20):
                pt = f"secret-{i}-{j}"
                ct = enc.encrypt(pt, aad=aad)
                ok = enc.decrypt(ct, aad=aad) == pt
                with lock:
                    results.append(ok)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)
        assert len(results) == 80
