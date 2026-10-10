"""Adversarial authorization tests for Phase 02.

Architecture Decisions: AD-010 (Zero-Trust), AD-020 (Policy-Governed
Agent Orchestration), AD-026 (Step-Up Authorization).

Tests: RBAC permission checks, privilege escalation prevention,
step-up enforcement for sensitive operations, session validation.
"""

from __future__ import annotations

from typing import Any

import pytest

from contracts.identity import TenantId, UserRole
from services.identity.auth import authenticate, register_user
from services.identity.authorization import (
    AuthorizationError,
    InsufficientPrivilegeError,
    Permission,
    StepUpRequiredError,
    TenantIsolationError,
    can_create_user,
    can_suspend_user,
    check_permission,
)
from services.identity.session import (
    grant_step_up,
    revoke_session,
    validate_session,
)
from services.identity.tenant import create_tenant


class TestAuthorization:
    def _setup(self) -> TenantId:
        """Create a tenant and return its ID."""
        tenant = create_tenant(name="Auth Test Tenant")
        return tenant.tenant_id

    def _create_user_with_role(
        self, tenant_id: TenantId, role: UserRole, email: str
    ) -> tuple[Any, Any]:
        """Create a user with a given role and return (user, session)."""
        register_user(
            tenant_id=tenant_id,
            email=email,
            password="test-password-123",
            role=role.value,
        )
        return authenticate(
            tenant_id=tenant_id,
            email=email,
            password="test-password-123",
        )

    def test_viewer_cannot_create_trade(self) -> None:
        """VIEWER lacks CREATE_TRADE permission."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(tenant_id, UserRole.VIEWER, "viewer@test.com")
        with pytest.raises(InsufficientPrivilegeError):
            check_permission(user, session, Permission.CREATE_TRADE)

    def test_trader_can_create_trade(self) -> None:
        """TRADER has CREATE_TRADE permission."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(tenant_id, UserRole.TRADER, "trader@test.com")
        # Should not raise
        check_permission(user, session, Permission.CREATE_TRADE)

    def test_trader_cannot_manage_risk_policy(self) -> None:
        """TRADER lacks MANAGE_RISK_POLICY permission."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(tenant_id, UserRole.TRADER, "trader@test.com")
        with pytest.raises(InsufficientPrivilegeError):
            check_permission(user, session, Permission.MANAGE_RISK_POLICY)

    def test_risk_manager_can_view_risk(self) -> None:
        """RISK_MANAGER has VIEW_RISK permission."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(
            tenant_id, UserRole.RISK_MANAGER, "risk@test.com"
        )
        check_permission(user, session, Permission.VIEW_RISK)

    def test_risk_manager_can_manage_risk_policy_with_step_up(self) -> None:
        """RISK_MANAGER can manage risk policy with step-up auth."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(
            tenant_id, UserRole.RISK_MANAGER, "risk@test.com"
        )
        # Without step-up: should raise
        with pytest.raises(StepUpRequiredError):
            check_permission(user, session, Permission.MANAGE_RISK_POLICY)
        # With step-up: should pass
        grant_step_up(session)
        check_permission(user, session, Permission.MANAGE_RISK_POLICY)

    def test_admin_cannot_manage_tenant(self) -> None:
        """ADMIN lacks MANAGE_TENANT permission (OWNER only)."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(tenant_id, UserRole.ADMIN, "admin@test.com")
        with pytest.raises(InsufficientPrivilegeError):
            check_permission(user, session, Permission.MANAGE_TENANT)

    def test_owner_can_manage_tenant_with_step_up(self) -> None:
        """OWNER can manage tenant with step-up auth."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(tenant_id, UserRole.OWNER, "owner@test.com")
        with pytest.raises(StepUpRequiredError):
            check_permission(user, session, Permission.MANAGE_TENANT)
        grant_step_up(session)
        check_permission(user, session, Permission.MANAGE_TENANT)

    def test_privilege_escalation_prevented(self) -> None:
        """can_create_user prevents same-level or higher role creation."""
        tenant_id = self._setup()
        admin, _ = self._create_user_with_role(tenant_id, UserRole.ADMIN, "admin@test.com")
        # Admin can create TRADER (lower)
        assert can_create_user(admin, UserRole.TRADER) is True
        # Admin cannot create OWNER (higher)
        assert can_create_user(admin, UserRole.OWNER) is False
        # Admin cannot create another ADMIN (same level)
        assert can_create_user(admin, UserRole.ADMIN) is False

    def test_owner_can_create_all_except_owner(self) -> None:
        """OWNER can create any role except another OWNER."""
        tenant_id = self._setup()
        owner, _ = self._create_user_with_role(tenant_id, UserRole.OWNER, "owner@test.com")
        assert can_create_user(owner, UserRole.ADMIN) is True
        assert can_create_user(owner, UserRole.RISK_MANAGER) is True
        assert can_create_user(owner, UserRole.TRADER) is True
        assert can_create_user(owner, UserRole.VIEWER) is True
        assert can_create_user(owner, UserRole.OWNER) is False

    def test_cross_tenant_permission_check(self) -> None:
        """Permission check rejects cross-tenant access."""
        tenant_a = create_tenant(name="Tenant A")
        tenant_b = create_tenant(name="Tenant B")
        user_a, session_a = self._create_user_with_role(
            tenant_a.tenant_id, UserRole.OWNER, "owner-a@test.com"
        )
        with pytest.raises(TenantIsolationError):
            check_permission(user_a, session_a, Permission.VIEW_DASHBOARD, tenant_b.tenant_id)

    def test_revoked_session_rejected(self) -> None:
        """Revoked sessions are rejected by check_permission."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(tenant_id, UserRole.VIEWER, "viewer@test.com")
        revoke_session(str(session.session_id))
        with pytest.raises(AuthorizationError):
            check_permission(user, session, Permission.VIEW_DASHBOARD)

    def test_unknown_permission_raises(self) -> None:
        """Unknown permission raises ValueError."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(tenant_id, UserRole.OWNER, "owner@test.com")
        with pytest.raises(ValueError):
            check_permission(user, session, "unknown_permission")

    def test_session_validation(self) -> None:
        """validate_session returns active sessions."""
        tenant_id = self._setup()
        _, session = self._create_user_with_role(tenant_id, UserRole.VIEWER, "viewer@test.com")
        validated = validate_session(str(session.session_id))
        assert validated.session_id == session.session_id

    def test_session_validation_rejected_for_revoked(self) -> None:
        """validate_session rejects revoked sessions."""
        tenant_id = self._setup()
        _, session = self._create_user_with_role(tenant_id, UserRole.VIEWER, "viewer@test.com")
        revoke_session(str(session.session_id))
        with pytest.raises(ValueError, match="revoked"):
            validate_session(str(session.session_id))

    def test_can_suspend_user_cross_tenant(self) -> None:
        """can_suspend_user returns False for cross-tenant."""
        tenant_a = create_tenant(name="Tenant A")
        tenant_b = create_tenant(name="Tenant B")
        owner_a = register_user(
            tenant_id=tenant_a.tenant_id,
            email="owner-a@test.com",
            password="pass-123",
            role=UserRole.OWNER.value,
        )
        user_b = register_user(
            tenant_id=tenant_b.tenant_id,
            email="user-b@test.com",
            password="pass-456",
            role=UserRole.VIEWER.value,
        )
        assert can_suspend_user(owner_a, user_b) is False

    def test_viewer_can_view_dashboard(self) -> None:
        """VIEWER has VIEW_DASHBOARD permission."""
        tenant_id = self._setup()
        user, session = self._create_user_with_role(tenant_id, UserRole.VIEWER, "viewer@test.com")
        check_permission(user, session, Permission.VIEW_DASHBOARD)
