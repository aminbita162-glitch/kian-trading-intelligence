"""E4 — Trust domain separation tests.

Per E4 (Safety Plane Hardening): separate kernel and vault trust domains.
The kernel's signing key is derived from KTI_RISK_TOKEN_KEY; the vault's
encryption key is derived from KTI_VAULT_KEY.  Neither component may
access the other's key material.

Tests:
- Env var names are distinct
- Kernel signer does not read KTI_VAULT_KEY
- Vault encryption does not read KTI_RISK_TOKEN_KEY
- Derived keys are different
- Trust domains are structurally separated
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from contracts.trust_domains import (
    KERNEL_KEY_ENV,
    TRUST_DOMAIN_KERNEL,
    TRUST_DOMAIN_VAULT,
    VAULT_KEY_ENV,
    derive_kernel_key_material,
    derive_vault_key_material,
    keys_are_distinct,
    trust_domains_are_separated,
)


class TestTrustDomainSeparation:
    """Test that kernel and vault trust domains are separated."""

    def test_env_vars_are_distinct(self) -> None:
        """KTI_RISK_TOKEN_KEY and KTI_VAULT_KEY must be different env vars."""
        assert KERNEL_KEY_ENV != VAULT_KEY_ENV
        assert KERNEL_KEY_ENV == "KTI_RISK_TOKEN_KEY"
        assert VAULT_KEY_ENV == "KTI_VAULT_KEY"

    def test_trust_domains_are_separated(self) -> None:
        """trust_domains_are_separated must return True."""
        assert trust_domains_are_separated()

    def test_trust_domain_identifiers_are_distinct(self) -> None:
        """Kernel and vault trust domain identifiers must differ."""
        assert TRUST_DOMAIN_KERNEL != TRUST_DOMAIN_VAULT
        assert TRUST_DOMAIN_KERNEL == "kernel"
        assert TRUST_DOMAIN_VAULT == "vault"

    def test_derived_keys_are_distinct(self) -> None:
        """Kernel and vault derived keys must be different."""
        kernel_key = derive_kernel_key_material()
        vault_key = derive_vault_key_material()
        assert keys_are_distinct(kernel_key, vault_key)
        assert kernel_key != vault_key

    def test_kernel_key_does_not_read_vault_env(self) -> None:
        """Kernel key derivation must not read KTI_VAULT_KEY."""
        # Set KTI_VAULT_KEY to a sentinel value
        with patch.dict(os.environ, {"KTI_VAULT_KEY": "vault-sentinel-key-1234567890"}):
            # Ensure KTI_RISK_TOKEN_KEY is not set to the same value
            env = os.environ.copy()
            env.pop("KTI_RISK_TOKEN_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                kernel_key = derive_kernel_key_material()
                # The kernel key should not contain the vault sentinel
                assert b"vault-sentinel-key" not in kernel_key

    def test_vault_key_does_not_read_kernel_env(self) -> None:
        """Vault key derivation must not read KTI_RISK_TOKEN_KEY."""
        with patch.dict(os.environ, {"KTI_RISK_TOKEN_KEY": "kernel-sentinel-key-1234567890"}):
            env = os.environ.copy()
            env.pop("KTI_VAULT_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                vault_key = derive_vault_key_material()
                # The vault key should not contain the kernel sentinel
                assert b"kernel-sentinel-key" not in vault_key

    def test_kernel_signer_uses_kernel_key_env(self) -> None:
        """RiskTokenSigner must read from KTI_RISK_TOKEN_KEY, not KTI_VAULT_KEY."""
        from contracts.risk_token import _load_risk_token_key

        with patch.dict(
            os.environ,
            {
                "KTI_RISK_TOKEN_KEY": "a" * 32,
                "KTI_VAULT_KEY": "b" * 32,
            },
        ):
            key = _load_risk_token_key()
            # The key is derived from "a"*32, not "b"*32
            import hashlib

            expected = hashlib.sha256(("a" * 32).encode()).digest()
            assert key == expected

    def test_vault_encryption_uses_vault_key_env(self) -> None:
        """EnvelopeEncryption must read from KTI_VAULT_KEY, not KTI_RISK_TOKEN_KEY."""
        from services.identity.encryption import _load_master_material

        with patch.dict(
            os.environ,
            {
                "KTI_RISK_TOKEN_KEY": "a" * 32,
                "KTI_VAULT_KEY": "b" * 32,
            },
        ):
            material = _load_master_material()
            # The material is derived from "b"*32, not "a"*32
            import hashlib

            expected = hashlib.sha256(("b" * 32).encode()).digest()
            assert material == expected

    def test_production_fail_closed_kernel(self) -> None:
        """Kernel key must fail-closed in production when KTI_RISK_TOKEN_KEY is missing."""
        from contracts.risk_token import RiskTokenKeyError, _load_risk_token_key

        env = os.environ.copy()
        env.pop("KTI_RISK_TOKEN_KEY", None)
        env["KTI_ENVIRONMENT"] = "production"
        with patch.dict(os.environ, env, clear=True), pytest.raises(RiskTokenKeyError):
            _load_risk_token_key()

    def test_production_fail_closed_vault(self) -> None:
        """Vault key must fail-closed in production when KTI_VAULT_KEY is missing."""
        from services.identity.encryption import EncryptionConfigurationError, _load_master_material

        env = os.environ.copy()
        env.pop("KTI_VAULT_KEY", None)
        env["KTI_ENVIRONMENT"] = "production"
        with patch.dict(os.environ, env, clear=True), pytest.raises(EncryptionConfigurationError):
            _load_master_material()
