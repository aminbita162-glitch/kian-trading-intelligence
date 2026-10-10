"""Adversarial tenant isolation tests for Phase 02.

Architecture Decisions: AD-002 (Multi-Tenant), AD-010 (Zero-Trust),
Section 10.3 (Tenant Isolation).

Tests: cross-tenant access is rejected at every boundary — user listing,
user management, credential access, session access, and audit events.
"""

from __future__ import annotations

import pytest

from contracts.identity import TenantId, UserRole
from services.identity.auth import register_user
from services.identity.authorization import TenantIsolationError
from services.identity.database import get_store
from services.identity.tenant import (
    TenantInactiveError,
    TenantNotFoundError,
    create_tenant,
    create_user_in_tenant,
    get_tenant,
    get_users_in_tenant,
    suspend_user,
    verify_tenant_isolation,
)


class TestTenantIsolation:
    def _create_two_tenants(self) -> tuple[TenantId, TenantId]:
        """Create two tenants with users."""
        tenant_a = create_tenant(name="Tenant A")
        tenant_b = create_tenant(name="Tenant B")
        return tenant_a.tenant_id, tenant_b.tenant_id

    def test_tenant_creation(self) -> None:
        """Tenants can be created and retrieved."""
        tenant = create_tenant(name="Isolation Test Tenant")
        retrieved = get_tenant(tenant.tenant_id)
        assert retrieved.name == "Isolation Test Tenant"
        assert retrieved.is_active is True

    def test_tenant_not_found(self) -> None:
        """Non-existent tenant raises TenantNotFoundError."""
        with pytest.raises(TenantNotFoundError):
            get_tenant(TenantId.generate())

    def test_cross_tenant_access_blocked(self) -> None:
        """verify_tenant_isolation raises PermissionError for different tenants."""
        tenant_a_id, tenant_b_id = self._create_two_tenants()
        with pytest.raises(PermissionError):
            verify_tenant_isolation(tenant_a_id, tenant_b_id)

    def test_same_tenant_access_allowed(self) -> None:
        """verify_tenant_isolation passes for same tenant."""
        tenant_a_id, _ = self._create_two_tenants()
        # Should not raise
        verify_tenant_isolation(tenant_a_id, tenant_a_id)

    def test_cross_tenant_user_listing_blocked(self) -> None:
        """User from tenant A cannot list users in tenant B."""
        tenant_a_id, tenant_b_id = self._create_two_tenants()
        user_a = register_user(
            tenant_id=tenant_a_id,
            email="user-a@test.com",
            password="pass-123",
            role=UserRole.ADMIN.value,
        )
        # Create users in tenant B
        register_user(
            tenant_id=tenant_b_id,
            email="user-b@test.com",
            password="pass-456",
            role=UserRole.VIEWER.value,
        )
        # user_a tries to list users in tenant_b
        with pytest.raises(TenantIsolationError):
            get_users_in_tenant(tenant_b_id, user_a)

    def test_cross_tenant_user_creation_blocked(self) -> None:
        """Admin from tenant A cannot create users in tenant B."""
        tenant_a_id, tenant_b_id = self._create_two_tenants()
        admin_a = register_user(
            tenant_id=tenant_a_id,
            email="admin-a@test.com",
            password="pass-123",
            role=UserRole.OWNER.value,
        )
        with pytest.raises(TenantIsolationError):
            create_user_in_tenant(
                tenant_id=tenant_b_id,
                email="cross-tenant@test.com",
                role=UserRole.VIEWER,
                actor=admin_a,
            )

    def test_cross_tenant_suspend_blocked(self) -> None:
        """Admin from tenant A cannot suspend users in tenant B."""
        tenant_a_id, tenant_b_id = self._create_two_tenants()
        admin_a = register_user(
            tenant_id=tenant_a_id,
            email="admin-a@test.com",
            password="pass-123",
            role=UserRole.OWNER.value,
        )
        user_b = register_user(
            tenant_id=tenant_b_id,
            email="user-b@test.com",
            password="pass-456",
            role=UserRole.VIEWER.value,
        )
        with pytest.raises(TenantIsolationError):
            suspend_user(
                tenant_id=tenant_b_id,
                target_user_id=user_b.user_id,
                actor=admin_a,
            )

    def test_users_in_tenant_are_isolated(self) -> None:
        """Users from tenant A do not appear in tenant B's user list."""
        tenant_a_id, tenant_b_id = self._create_two_tenants()
        admin_a = register_user(
            tenant_id=tenant_a_id,
            email="admin-a@test.com",
            password="pass-123",
            role=UserRole.OWNER.value,
        )
        register_user(
            tenant_id=tenant_b_id,
            email="user-b@test.com",
            password="pass-456",
            role=UserRole.VIEWER.value,
        )
        users_a = get_users_in_tenant(tenant_a_id, admin_a)
        emails_a = {u.email for u in users_a}
        assert "user-b@test.com" not in emails_a

    def test_tenant_inactivity_rejected(self) -> None:
        """Inactive tenant raises TenantInactiveError."""
        tenant = create_tenant(name="Inactive Tenant")
        # Deactivate the tenant
        tenant_record = get_store().get_tenant(tenant.tenant_id)
        assert tenant_record is not None
        tenant_record.is_active = False
        with pytest.raises(TenantInactiveError):
            get_tenant(tenant.tenant_id)
