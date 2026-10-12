"""Tests for TOTP and MFA flows (E1 deliverable).

Architecture Decisions: AD-010 (Zero-Trust), AD-026 (Step-Up Authorization).
"""

from __future__ import annotations

import pytest

from contracts.identity import Tenant, User, UserRole
from services.identity.auth import register_user
from services.identity.database import get_store
from services.identity.mfa import (
    MFAError,
    disable_mfa_for_user,
    enable_mfa_for_user,
    verify_mfa_for_user,
)
from services.identity.tenant import create_tenant
from services.identity.totp import (
    generate_totp_provisioning_uri,
    generate_totp_secret,
    get_current_totp_code,
    verify_totp,
)


class TestTOTP:
    """Test TOTP generation, verification, and provisioning URI."""

    def test_generate_totp_secret_returns_base32(self) -> None:
        """Generated TOTP secret is a non-empty base32 string."""
        secret = generate_totp_secret()
        assert len(secret) > 0
        # base32 characters: A-Z, 2-7
        for ch in secret:
            assert ch.isalnum()

    def test_generate_totp_secret_is_unique(self) -> None:
        """Two generated secrets are different."""
        s1 = generate_totp_secret()
        s2 = generate_totp_secret()
        assert s1 != s2

    def test_get_current_totp_code_is_six_digits(self) -> None:
        """Current TOTP code is exactly 6 digits."""
        secret = generate_totp_secret()
        code = get_current_totp_code(secret)
        assert len(code) == 6
        assert code.isdigit()

    def test_verify_totp_valid_code(self) -> None:
        """Valid TOTP code passes verification."""
        secret = generate_totp_secret()
        code = get_current_totp_code(secret)
        assert verify_totp(secret, code) is True

    def test_verify_totp_invalid_code(self) -> None:
        """Invalid TOTP code fails verification."""
        secret = generate_totp_secret()
        code = get_current_totp_code(secret)
        wrong = "000000" if code != "000000" else "111111"
        assert verify_totp(secret, wrong) is False

    def test_verify_totp_wrong_secret(self) -> None:
        """Code from one secret fails with another secret."""
        s1 = generate_totp_secret()
        s2 = generate_totp_secret()
        code = get_current_totp_code(s1)
        assert verify_totp(s2, code) is False

    def test_provisioning_uri_format(self) -> None:
        """Provisioning URI has the correct format."""
        secret = generate_totp_secret()
        uri = generate_totp_provisioning_uri(
            email="user@test.com",
            secret=secret,
        )
        assert uri.startswith("otpauth://totp/")
        assert "secret=" + secret in uri or f"secret={secret}" in uri
        assert "Kian+Trading+Intelligence" in uri or "Kian%20Trading%20Intelligence" in uri


class TestMFAFlow:
    """Test MFA enable/verify/disable flow."""

    def _setup(self) -> tuple[Tenant, User]:
        """Create a tenant and register a user."""
        tenant = create_tenant(name="MFA Flow Test Tenant")
        user = register_user(
            tenant_id=tenant.tenant_id,
            email="mfaflow@test.com",
            password="test-password-12345",
            role=UserRole.ADMIN.value,
        )
        return tenant, user

    def test_enable_mfa_returns_secret_and_uri(self) -> None:
        """enable_mfa_for_user returns a secret and provisioning URI."""
        tenant, user = self._setup()
        secret, uri = enable_mfa_for_user(tenant.tenant_id, user.user_id)
        assert len(secret) > 0
        assert uri.startswith("otpauth://totp/")

    def test_enable_mfa_sets_user_flags(self) -> None:
        """Enabling MFA sets the user's mfa_enabled flag."""
        tenant, user = self._setup()
        enable_mfa_for_user(tenant.tenant_id, user.user_id)
        updated = get_store().get_user(user.user_id)
        assert updated is not None
        assert updated.mfa_enabled is True
        assert updated.mfa_secret is not None

    def test_verify_mfa_valid_code(self) -> None:
        """Valid MFA code passes verification."""
        tenant, user = self._setup()
        secret, _ = enable_mfa_for_user(tenant.tenant_id, user.user_id)
        code = get_current_totp_code(secret)
        assert verify_mfa_for_user(tenant.tenant_id, user.user_id, code) is True

    def test_verify_mfa_invalid_code_raises(self) -> None:
        """Invalid MFA code raises MFAError."""
        tenant, user = self._setup()
        enable_mfa_for_user(tenant.tenant_id, user.user_id)
        with pytest.raises(MFAError):
            verify_mfa_for_user(tenant.tenant_id, user.user_id, "000000")

    def test_disable_mfa_clears_settings(self) -> None:
        """Disabling MFA clears the user's MFA settings."""
        tenant, user = self._setup()
        enable_mfa_for_user(tenant.tenant_id, user.user_id)
        disable_mfa_for_user(tenant.tenant_id, user.user_id)
        updated = get_store().get_user(user.user_id)
        assert updated is not None
        assert updated.mfa_enabled is False
        assert updated.mfa_secret is None

    def test_verify_mfa_not_enabled_raises(self) -> None:
        """Verifying MFA on a user without MFA raises MFAError."""
        tenant, user = self._setup()
        with pytest.raises(MFAError):
            verify_mfa_for_user(tenant.tenant_id, user.user_id, "123456")
