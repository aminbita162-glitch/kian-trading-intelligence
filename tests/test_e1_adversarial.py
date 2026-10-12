"""E1 adversarial security tests for Kian Trading Intelligence.

Tests cross-tenant credential rejection, tamper detection, AAD mismatch,
deny-by-default policy, password migration, TOTP verification, session
rotation, KMS key provider separation, and legacy hash detection.
"""

from __future__ import annotations

import base64
import hashlib
import json
from uuid import uuid4

import pytest

from contracts.identity import (
    CredentialType,
    SessionStatus,
    Tenant,
    TenantId,
    User,
    UserRole,
)
from contracts.policy import PolicyEffect
from services.identity.auth import (
    _hash_password,
    _hash_password_pbkdf2,
    generate_salt,
    is_legacy_password_hash,
    migrate_password_hash,
)
from services.identity.credential_vault import (
    CredentialAccessDeniedError,
    retrieve_credential,
    store_credential,
)
from services.identity.encryption import (
    DecryptionError,
    KMSKeyProvider,
    LocalKeyProvider,
    get_encryption,
    reset_encryption,
)
from services.identity.persistence import PersistentIdentityStore
from services.identity.policy_engine import get_policy_engine, reset_policy_engine
from services.identity.session import create_session, get_session, rotate_session_token
from services.identity.totp import generate_totp_secret, get_current_totp_code, verify_totp


class TestCrossTenantCredentialAccess:
    """Test that cross-tenant credential access is rejected."""

    def test_cross_tenant_credential_access_rejected_api(self) -> None:
        """Cross-tenant credential access is rejected at the API level."""
        reset_encryption()
        store = PersistentIdentityStore()
        tenant_a = Tenant.create(name="Adversarial Tenant A")
        tenant_b = Tenant.create(name="Adversarial Tenant B")
        store.create_tenant(tenant_a)
        store.create_tenant(tenant_b)

        user_a = User.create(
            tenant_id=tenant_a.tenant_id,
            email="adv-a@test.com",
            role=UserRole.ADMIN,
        )
        user_b = User.create(
            tenant_id=tenant_b.tenant_id,
            email="adv-b@test.com",
            role=UserRole.ADMIN,
        )
        store.create_user(user_a)
        store.create_user(user_b)

        entry_id = store_credential(
            tenant_id=tenant_a.tenant_id,
            user_id=user_a.user_id,
            credential_type=CredentialType.EXCHANGE_API_KEY,
            label="Tenant A Secret",
            secret_value="tenant-a-secret-key-12345",
        )

        with pytest.raises(CredentialAccessDeniedError):
            retrieve_credential(
                entry_id=entry_id,
                tenant_id=tenant_b.tenant_id,
                user_id=user_b.user_id,
            )

    def test_cross_tenant_user_access_rejected_db(self) -> None:
        """Cross-tenant user access is rejected at the DB level."""
        store = PersistentIdentityStore()
        tenant_a = Tenant.create(name="DB Isolation Tenant A")
        tenant_b = Tenant.create(name="DB Isolation Tenant B")
        store.create_tenant(tenant_a)
        store.create_tenant(tenant_b)

        user_a = User.create(
            tenant_id=tenant_a.tenant_id,
            email="db-iso-a@test.com",
            role=UserRole.VIEWER,
        )
        store.create_user(user_a)

        # Searching for user_a's email in tenant_b should return None
        found = store.get_user_by_email(tenant_b.tenant_id, "db-iso-a@test.com")
        assert found is None


class TestTamperDetection:
    """Test that tampered ciphertext and AAD mismatch fail-closed."""

    def test_tampered_ciphertext_raises_decryption_error(self) -> None:
        """Tampering with ciphertext raises DecryptionError (fail-closed)."""
        reset_encryption()
        enc = get_encryption()
        ciphertext = enc.encrypt("secret-value-12345", aad=b"ctx")
        env = json.loads(ciphertext)
        ct_bytes = bytearray(base64.b64decode(env["c"]))
        ct_bytes[0] ^= 0xFF
        env["c"] = base64.b64encode(bytes(ct_bytes)).decode()
        tampered = json.dumps(env)
        with pytest.raises(DecryptionError):
            enc.decrypt(tampered, aad=b"ctx")

    def test_aad_mismatch_raises_decryption_error(self) -> None:
        """AAD mismatch raises DecryptionError (fail-closed)."""
        reset_encryption()
        enc = get_encryption()
        ciphertext = enc.encrypt("secret-value-12345", aad=b"tenant:A|user:X")
        with pytest.raises(DecryptionError):
            enc.decrypt(ciphertext, aad=b"tenant:B|user:Y")


class TestPolicyEngineDenyByDefault:
    """Test deny-by-default policy engine behavior."""

    def test_deny_by_default_rejects_unknown_action(self) -> None:
        """Deny-by-default rejects unknown actions."""
        reset_policy_engine()
        engine = get_policy_engine()
        decision = engine.evaluate(
            subject={"role": "viewer", "tenant_id": "t1"},
            action="delete_all",
            resource="everything",
        )
        assert decision.effect == PolicyEffect.DENY

    def test_policy_engine_allows_configured_rules(self) -> None:
        """Configured rules allow matching requests."""
        reset_policy_engine()
        engine = get_policy_engine()
        decision = engine.evaluate(
            subject={"role": "viewer", "tenant_id": "t1"},
            action="read",
            resource="user/profile",
        )
        assert decision.effect == PolicyEffect.ALLOW


class TestPasswordMigration:
    """Test password hash migration from PBKDF2 to scrypt."""

    def test_old_pbkdf2_hash_can_be_migrated(self) -> None:
        """Old PBKDF2 password hash can be migrated to scrypt."""
        password = "my-password-12345"
        salt = generate_salt()
        legacy_hash = _hash_password_pbkdf2(password, salt)
        assert is_legacy_password_hash(legacy_hash) is True

        migrated = migrate_password_hash(password, legacy_hash)
        assert migrated.startswith("scrypt")
        assert not is_legacy_password_hash(migrated)

    def test_scrypt_password_hash_verification(self) -> None:
        """Scrypt password hash verification works."""
        password = "verify-me-12345"
        salt = generate_salt()
        hashed = _hash_password(password, salt)
        assert hashed.startswith("scrypt")
        assert is_legacy_password_hash(hashed) is False

    def test_legacy_password_hash_detection(self) -> None:
        """Legacy password hash detection works."""
        salt = generate_salt()
        legacy = _hash_password_pbkdf2("pass", salt)
        modern = _hash_password("pass", generate_salt())
        assert is_legacy_password_hash(legacy) is True
        assert is_legacy_password_hash(modern) is False


class TestTOTPVerification:
    """Test TOTP verification accepts valid and rejects invalid codes."""

    def test_totp_accepts_valid_code(self) -> None:
        """TOTP verification accepts a valid code."""
        secret = generate_totp_secret()
        code = get_current_totp_code(secret)
        assert verify_totp(secret, code) is True

    def test_totp_rejects_invalid_code(self) -> None:
        """TOTP verification rejects an invalid code."""
        secret = generate_totp_secret()
        code = get_current_totp_code(secret)
        wrong = "000000" if code != "000000" else "111111"
        assert verify_totp(secret, wrong) is False


class TestSessionRotation:
    """Test session token rotation revokes old token."""

    def test_session_rotation_revokes_old_token(self) -> None:
        """Session token rotation revokes the old token."""
        tenant_id = TenantId.generate()

        user_id = uuid4()
        session = create_session(
            tenant_id=tenant_id,
            user_id=user_id,  # type: ignore[arg-type]
        )
        old_id = str(session.session_id)

        new_session = rotate_session_token(old_id)
        assert str(new_session.session_id) != old_id

        old = get_session(old_id)
        assert old is not None
        assert old.status == SessionStatus.REVOKED


class TestKMSKeyProvider:
    """Test KMS key provider produces different keys than local."""

    def test_kms_provider_different_from_local(self) -> None:
        """KMS key provider produces a different key than local provider."""
        material = hashlib.sha256(b"kms-vs-local-test-material").digest()
        local = LocalKeyProvider(material)
        kms = KMSKeyProvider(material, backend="test-backend")
        local_key = local.get_key(1)
        kms_key = kms.get_key(1)
        assert local_key != kms_key
        assert kms.get_key_id() == "kms"
        assert local.get_key_id() == "local-dev"
