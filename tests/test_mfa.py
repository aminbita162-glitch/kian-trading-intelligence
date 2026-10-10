"""Adversarial MFA and step-up authentication tests for Phase 02.

Architecture Decisions: AD-010 (Zero-Trust), AD-026 (Step-Up Authorization).

Tests: MFA enable/disable, TOTP generation and verification, step-up grant,
MFA failure handling, and method mismatch detection.
"""

from __future__ import annotations

from typing import Any

import pytest

from contracts.identity import MFAMethod, UserRole
from services.identity.auth import authenticate, register_user
from services.identity.mfa import (
    MFAError,
    MFAMethodMismatchError,
    MFANotEnabledError,
    disable_mfa,
    enable_mfa,
    generate_mfa_secret,
    generate_totp_code,
    verify_mfa,
    verify_totp_code,
)
from services.identity.session import check_step_up, grant_step_up
from services.identity.tenant import create_tenant


class TestMFA:
    def _setup_user(self) -> tuple[Any, Any]:
        """Create a tenant, register a user, and authenticate."""
        tenant = create_tenant(name="MFA Test Tenant")
        register_user(
            tenant_id=tenant.tenant_id,
            email="mfa@test.com",
            password="test-password-123",
            role=UserRole.TRADER.value,
        )
        user, session = authenticate(
            tenant_id=tenant.tenant_id,
            email="mfa@test.com",
            password="test-password-123",
        )
        return user, session

    def test_generate_mfa_secret(self) -> None:
        """Generated MFA secret is a non-empty hex string."""
        secret = generate_mfa_secret()
        assert len(secret) > 0
        int(secret, 16)  # Should not raise

    def test_totp_code_is_six_digits(self) -> None:
        """TOTP code is exactly 6 digits."""
        secret = generate_mfa_secret()
        code = generate_totp_code(secret, timestamp=1000000)
        assert len(code) == 6
        assert code.isdigit()

    def test_totp_code_deterministic(self) -> None:
        """Same secret + timestamp produces same code."""
        secret = generate_mfa_secret()
        code1 = generate_totp_code(secret, timestamp=1000000)
        code2 = generate_totp_code(secret, timestamp=1000000)
        assert code1 == code2

    def test_totp_code_different_secrets(self) -> None:
        """Different secrets produce different codes (with high probability)."""
        secret1 = generate_mfa_secret()
        secret2 = generate_mfa_secret()
        code1 = generate_totp_code(secret1, timestamp=1000000)
        code2 = generate_totp_code(secret2, timestamp=1000000)
        assert code1 != code2

    def test_verify_totp_code_valid(self) -> None:
        """Valid TOTP code passes verification."""
        secret = generate_mfa_secret()
        code = generate_totp_code(secret)
        assert verify_totp_code(secret, code) is True

    def test_verify_totp_code_invalid(self) -> None:
        """Invalid TOTP code fails verification."""
        secret = generate_mfa_secret()
        real_code = generate_totp_code(secret)
        wrong_code = "000000" if real_code != "000000" else "111111"
        assert verify_totp_code(secret, wrong_code) is False

    def test_verify_totp_code_wrong_secret(self) -> None:
        """Code from one secret fails with another secret."""
        secret1 = generate_mfa_secret()
        secret2 = generate_mfa_secret()
        code1 = generate_totp_code(secret1)
        assert verify_totp_code(secret2, code1) is False

    def test_enable_mfa(self) -> None:
        """Enabling MFA sets the user's mfa_enabled flag."""
        user, _ = self._setup_user()
        secret = enable_mfa(user, MFAMethod.TOTP)
        assert user.mfa_enabled is True
        assert user.mfa_method == MFAMethod.TOTP
        assert user.mfa_secret == secret

    def test_disable_mfa(self) -> None:
        """Disabling MFA clears the user's MFA settings."""
        user, _ = self._setup_user()
        enable_mfa(user, MFAMethod.TOTP)
        disable_mfa(user)
        assert user.mfa_enabled is False
        assert user.mfa_method is None
        assert user.mfa_secret is None

    def test_verify_mfa_not_enabled(self) -> None:
        """Verifying MFA on a user without MFA raises MFANotEnabledError."""
        user, session = self._setup_user()
        with pytest.raises(MFANotEnabledError):
            verify_mfa(session, user, "123456")

    def test_verify_mfa_success_grants_step_up(self) -> None:
        """Successful MFA verification grants step-up authorization."""
        user, session = self._setup_user()
        secret = enable_mfa(user, MFAMethod.TOTP)
        code = generate_totp_code(secret)
        result = verify_mfa(session, user, code)
        assert result is True
        assert check_step_up(session) is True

    def test_verify_mfa_invalid_code(self) -> None:
        """Invalid MFA code raises MFAError and does not grant step-up."""
        user, session = self._setup_user()
        enable_mfa(user, MFAMethod.TOTP)
        # Generate a code from a different secret to ensure mismatch
        other_secret = generate_mfa_secret()
        wrong_code = generate_totp_code(other_secret)
        # It's very unlikely two different secrets produce the same code
        if wrong_code == generate_totp_code(user.mfa_secret or ""):
            wrong_code = "999999"
        with pytest.raises(MFAError):
            verify_mfa(session, user, wrong_code)
        assert check_step_up(session) is False

    def test_verify_mfa_method_mismatch(self) -> None:
        """Wrong MFA method raises MFAMethodMismatchError."""
        user, session = self._setup_user()
        enable_mfa(user, MFAMethod.TOTP)
        code = generate_totp_code(user.mfa_secret or "")
        with pytest.raises(MFAMethodMismatchError):
            verify_mfa(session, user, code, method=MFAMethod.SMS)

    def test_step_up_grant_and_check(self) -> None:
        """grant_step_up sets step-up, check_step_up returns True."""
        user, session = self._setup_user()
        assert check_step_up(session) is False
        grant_step_up(session)
        assert check_step_up(session) is True

    def test_step_up_requires_explicit_grant(self) -> None:
        """Step-up is not active until explicitly granted."""
        user, session = self._setup_user()
        assert check_step_up(session) is False
        grant_step_up(session)
        assert check_step_up(session) is True
