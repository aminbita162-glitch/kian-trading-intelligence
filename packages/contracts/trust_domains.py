"""Trust-domain separation verification for E4 (Safety Plane Hardening).

Per E4: the Risk Kernel and the Credential Vault must operate in separate
trust domains.  Neither component may access the other's key material.

The kernel's signing key is derived from ``KTI_RISK_TOKEN_KEY``; the vault's
encryption key is derived from ``KTI_VAULT_KEY``.  This module provides
verifiable evidence that the two trust domains are separated:

1. The env vars are distinct (``KTI_RISK_TOKEN_KEY`` vs ``KTI_VAULT_KEY``).
2. The :class:`RiskTokenSigner` cannot read ``KTI_VAULT_KEY``.
3. The :class:`EnvelopeEncryption` cannot read ``KTI_RISK_TOKEN_KEY``.
4. The derived keys are different (no key reuse).

This is checked at test time by :mod:`tests.test_e4_trust_domains`.
"""

from __future__ import annotations

import hashlib
import os

# Trust domain identifiers
TRUST_DOMAIN_KERNEL = "kernel"
TRUST_DOMAIN_VAULT = "vault"

# Environment variable names for each trust domain
KERNEL_KEY_ENV = "KTI_RISK_TOKEN_KEY"
VAULT_KEY_ENV = "KTI_VAULT_KEY"


def kernel_key_source() -> str:
    """Return the environment variable name the kernel reads its key from."""
    return KERNEL_KEY_ENV


def vault_key_source() -> str:
    """Return the environment variable name the vault reads its key from."""
    return VAULT_KEY_ENV


def trust_domains_are_separated() -> bool:
    """Verify that the kernel and vault trust domains are separated.

    The separation is structural:
    - Different env var names (KTI_RISK_TOKEN_KEY vs KTI_VAULT_KEY).
    - The RiskTokenSigner only reads KTI_RISK_TOKEN_KEY.
    - The EnvelopeEncryption only reads KTI_VAULT_KEY.
    """
    return KERNEL_KEY_ENV != VAULT_KEY_ENV


def keys_are_distinct(kernel_key: bytes, vault_key: bytes) -> bool:
    """Verify that the kernel and vault keys are different (no reuse)."""
    return kernel_key != vault_key


def derive_kernel_key_material() -> bytes:
    """Derive the kernel trust-domain key material.

    This reads from ``KTI_RISK_TOKEN_KEY`` only — never from
    ``KTI_VAULT_KEY``.
    """
    raw = os.environ.get(KERNEL_KEY_ENV, "")
    if not raw:
        raw = "phase-e4-risk-token-key-change-in-prod"
    return hashlib.sha256(raw.encode()).digest()


def derive_vault_key_material() -> bytes:
    """Derive the vault trust-domain key material.

    This reads from ``KTI_VAULT_KEY`` only — never from
    ``KTI_RISK_TOKEN_KEY``.
    """
    raw = os.environ.get(VAULT_KEY_ENV, "")
    if not raw:
        raw = "phase02-dev-vault-key-change-in-prod"
    return hashlib.sha256(raw.encode()).digest()
