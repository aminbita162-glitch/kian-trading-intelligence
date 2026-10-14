"""Tests for KMS key provider and encryption factory (E1 deliverable).

Architecture Decisions: AD-019 (Non-Custodial Credential Vault),
Section 10.2 (Secrets — managed encryption).
"""

from __future__ import annotations

import hashlib

import pytest

from services.identity.encryption import (
    DecryptionError,
    EnvelopeEncryption,
    KMSKeyProvider,
    LocalKeyProvider,
    get_key_provider,
    reset_encryption,
)


class TestKMSKeyProvider:
    """Test the KMS key provider interface."""

    def test_kms_provider_implements_protocol(self) -> None:
        """KMSKeyProvider implements the KeyProvider protocol."""
        material = hashlib.sha256(b"kms-test-material-for-32-bytes!").digest()
        provider = KMSKeyProvider(material)
        assert hasattr(provider, "get_key")
        assert hasattr(provider, "get_current_version")
        assert hasattr(provider, "get_key_id")

    def test_kms_key_id_is_kms(self) -> None:
        """KMS provider key_id is 'kms'."""
        material = hashlib.sha256(b"kms-test-material-for-32-bytes!").digest()
        provider = KMSKeyProvider(material)
        assert provider.get_key_id() == "kms"

    def test_kms_provider_encrypt_decrypt_roundtrip(self) -> None:
        """KMS provider encrypt/decrypt roundtrip works."""
        material = hashlib.sha256(b"kms-roundtrip-test-material!!!").digest()
        provider = KMSKeyProvider(material)
        enc = EnvelopeEncryption(provider)
        plaintext = "kms-encrypted-secret-value-12345"
        aad = b"tenant:t1|user:u1"
        ciphertext = enc.encrypt(plaintext, aad=aad)
        assert ciphertext != plaintext
        decrypted = enc.decrypt(ciphertext, aad=aad)
        assert decrypted == plaintext

    def test_kms_provider_aad_mismatch_fails(self) -> None:
        """KMS provider AAD mismatch raises DecryptionError."""
        material = hashlib.sha256(b"kms-aad-test-material-1234567890!").digest()
        provider = KMSKeyProvider(material)
        enc = EnvelopeEncryption(provider)
        ciphertext = enc.encrypt("secret", aad=b"tenant:A|user:X")
        with pytest.raises(DecryptionError):
            enc.decrypt(ciphertext, aad=b"tenant:B|user:Y")

    def test_kms_provider_different_keys_per_backend(self) -> None:
        """Different KMS backends produce different keys."""
        material = hashlib.sha256(b"backend-diff-test-material-1234567").digest()
        kms_a = KMSKeyProvider(material, backend="aws-kms")
        kms_b = KMSKeyProvider(material, backend="gcp-kms")
        assert kms_a.get_key(1) != kms_b.get_key(1)


class TestKeyProviderFactory:
    """Test the get_key_provider() factory."""

    def test_factory_returns_local_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Factory returns LocalKeyProvider when KTI_KMS_PROVIDER is not set."""
        monkeypatch.delenv("KTI_KMS_PROVIDER", raising=False)
        monkeypatch.delenv("KTI_ENVIRONMENT", raising=False)
        reset_encryption()
        provider = get_key_provider()
        assert isinstance(provider, LocalKeyProvider)

    def test_factory_returns_kms_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Factory returns KMSKeyProvider when KTI_KMS_PROVIDER is set."""
        monkeypatch.setenv("KTI_KMS_PROVIDER", "1")
        monkeypatch.delenv("KTI_ENVIRONMENT", raising=False)
        reset_encryption()
        provider = get_key_provider()
        assert isinstance(provider, KMSKeyProvider)

    def test_factory_returns_kms_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Factory returns KMSKeyProvider in production."""
        monkeypatch.delenv("KTI_KMS_PROVIDER", raising=False)
        monkeypatch.setenv("KTI_ENVIRONMENT", "production")
        monkeypatch.setenv(
            "KTI_VAULT_KEY",
            "a-very-long-production-vault-key-32+bytes!",
        )
        reset_encryption()
        provider = get_key_provider()
        assert isinstance(provider, KMSKeyProvider)
        monkeypatch.delenv("KTI_ENVIRONMENT", raising=False)
        reset_encryption()

    def test_kms_produces_different_key_than_local(self) -> None:
        """KMS key provider produces a different key than local provider."""
        material = hashlib.sha256(b"shared-material-for-key-diff-test").digest()
        local = LocalKeyProvider(material)
        kms = KMSKeyProvider(material, backend="simulated")
        assert local.get_key(1) != kms.get_key(1)
