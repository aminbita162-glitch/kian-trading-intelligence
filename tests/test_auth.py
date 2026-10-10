"""Adversarial authentication tests for Phase 02.

Architecture Decisions: AD-010 (Zero-Trust), AD-026 (Step-Up Authorization).

Tests: successful authentication, invalid credentials, account lockout,
cross-tenant authentication rejection, inactive account rejection,
password verification, and session creation.
"""

from __future__ import annotations

import pytest

from contracts.identity import TenantId, UserRole
from services.identity.auth import (
    MAX_FAILED_ATTEMPTS,
    AccountInactiveError,
    AccountLockedError,
    AuthenticationError,
    authenticate,
    register_user,
    verify_password,
)
from services.identity.authorization import (
    TenantIsolationError,
    check_tenant_access,
)
from services.identity.database import get_store
from services.identity.tenant import create_tenant, suspend_user


class TestAuthentication:
    def _setup_tenant_and_user(self) -> tuple[TenantId, str]:
        """Create a tenant and registered user for testing."""
        tenant = create_tenant(name="Test Tenant")
        register_user(
            tenant_id=tenant.tenant_id,
            email="user@test.com",
            password="secure-password-123",
            role=UserRole.TRADER.value,
        )
        return tenant.tenant_id, "user@test.com"

    def test_successful_authentication(self) -> None:
        """Valid credentials produce a session."""
        tenant_id, email = self._setup_tenant_and_user()
        user, session = authenticate(
            tenant_id=tenant_id,
            email=email,
            password="secure-password-123",
        )
        assert user.email == email
        assert session.user_id == user.user_id
        assert session.tenant_id == tenant_id

    def test_invalid_password(self) -> None:
        """Wrong password raises AuthenticationError."""
        tenant_id, email = self._setup_tenant_and_user()
        with pytest.raises(AuthenticationError):
            authenticate(
                tenant_id=tenant_id,
                email=email,
                password="wrong-password",
            )

    def test_nonexistent_user(self) -> None:
        """Non-existent email raises AuthenticationError."""
        tenant_id, _ = self._setup_tenant_and_user()
        with pytest.raises(AuthenticationError):
            authenticate(
                tenant_id=tenant_id,
                email="nobody@test.com",
                password="any-password",
            )

    def test_account_lockout_after_max_failures(self) -> None:
        """Account locks after MAX_FAILED_ATTEMPTS failed attempts."""
        tenant_id, email = self._setup_tenant_and_user()
        for _ in range(MAX_FAILED_ATTEMPTS):
            with pytest.raises(AuthenticationError):
                authenticate(
                    tenant_id=tenant_id,
                    email=email,
                    password="wrong",
                )
        # Now account should be locked
        with pytest.raises(AccountLockedError):
            authenticate(
                tenant_id=tenant_id,
                email=email,
                password="secure-password-123",
            )

    def test_inactive_account_rejected(self) -> None:
        """Inactive account raises AccountInactiveError."""
        tenant_id, email = self._setup_tenant_and_user()
        # Create an actor with sufficient privilege to suspend
        actor = register_user(
            tenant_id=tenant_id,
            email="admin@test.com",
            password="admin-pass-123",
            role=UserRole.OWNER.value,
        )
        user = get_store().get_user_by_email(tenant_id, email)
        assert user is not None
        suspend_user(
            tenant_id=tenant_id,
            target_user_id=user.user_id,
            actor=actor,
        )
        with pytest.raises(AccountInactiveError):
            authenticate(
                tenant_id=tenant_id,
                email=email,
                password="secure-password-123",
            )

    def test_cross_tenant_authentication_rejected(self) -> None:
        """User from tenant A cannot authenticate under tenant B."""
        tenant_id_a, email = self._setup_tenant_and_user()
        tenant_b = create_tenant(name="Tenant B")
        # The user does not exist in tenant B, so it should fail
        with pytest.raises(AuthenticationError):
            authenticate(
                tenant_id=tenant_b.tenant_id,
                email=email,
                password="secure-password-123",
            )

    def test_password_verification(self) -> None:
        """verify_password returns True for correct password."""
        tenant_id, _ = self._setup_tenant_and_user()
        user = get_store().get_user_by_email(tenant_id, "user@test.com")
        assert user is not None
        assert verify_password(user.user_id, "secure-password-123") is True
        assert verify_password(user.user_id, "wrong") is False

    def test_failed_count_reset_on_success(self) -> None:
        """Failed login count resets to 0 on successful login."""
        tenant_id, email = self._setup_tenant_and_user()
        # One failed attempt
        with pytest.raises(AuthenticationError):
            authenticate(
                tenant_id=tenant_id,
                email=email,
                password="wrong",
            )
        user = get_store().get_user_by_email(tenant_id, email)
        assert user is not None
        assert user.failed_login_count == 1
        # Successful login resets
        authenticate(
            tenant_id=tenant_id,
            email=email,
            password="secure-password-123",
        )
        user = get_store().get_user_by_email(tenant_id, email)
        assert user is not None
        assert user.failed_login_count == 0

    def test_device_registration_on_auth(self) -> None:
        """Device fingerprint is registered during auth."""
        tenant_id, email = self._setup_tenant_and_user()
        _, session = authenticate(
            tenant_id=tenant_id,
            email=email,
            password="secure-password-123",
            device_fingerprint="device-abc-123",
        )
        assert session.device_id is not None

    def test_cross_tenant_access_isolation(self) -> None:
        """TenantIsolationError is the correct exception for cross-tenant."""
        tenant_a = create_tenant(name="Tenant A")
        tenant_b = create_tenant(name="Tenant B")
        user_a = register_user(
            tenant_id=tenant_a.tenant_id,
            email="user-a@test.com",
            password="pass-123",
            role=UserRole.OWNER.value,
        )
        # Verify that check_tenant_access raises for cross-tenant
        with pytest.raises(TenantIsolationError):
            check_tenant_access(user_a, tenant_b.tenant_id)
