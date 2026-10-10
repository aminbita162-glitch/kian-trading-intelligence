"""Tenant management and isolation service for Kian Trading Intelligence.

Architecture Decisions: AD-002 (Multi-Tenant Foundation), AD-010 (Zero-Trust).

Per AD-002: tenant isolation designed from inception. Every record is
tenant-scoped. Cross-tenant access is tested and rejected.

Per Section 10.3: cross-tenant access attempts must be tested and rejected.
"""

from __future__ import annotations

from contracts.identity import (
    AuditEventType,
    Tenant,
    TenantId,
    User,
    UserId,
    UserRole,
)
from services.identity.audit import audit
from services.identity.auth import register_user
from services.identity.authorization import (
    InsufficientPrivilegeError,
    can_create_user,
    can_suspend_user,
    check_tenant_access,
)
from services.identity.database import get_store


class TenantError(Exception):
    """Raised when tenant operations fail."""


class TenantNotFoundError(TenantError):
    """Raised when a tenant is not found."""


class TenantInactiveError(TenantError):
    """Raised when a tenant is inactive."""


def create_tenant(*, name: str) -> Tenant:
    """Create a new tenant.

    Per AD-002: tenants are the isolation boundary.
    """
    tenant = Tenant.create(name=name)
    store = get_store()
    store.create_tenant(tenant)

    audit(
        event_type=AuditEventType.TENANT_CREATED,
        tenant_id=tenant.tenant_id,
        detail=f"Tenant created: {name}",
    )

    return tenant


def get_tenant(tenant_id: TenantId) -> Tenant:
    """Get a tenant by ID. Raises if not found or inactive."""
    tenant = get_store().get_tenant(tenant_id)
    if tenant is None:
        raise TenantNotFoundError(f"Tenant not found: {tenant_id}")
    if not tenant.is_active:
        raise TenantInactiveError(f"Tenant is inactive: {tenant_id}")
    return tenant


def verify_tenant_isolation(
    user_tenant_id: TenantId,
    resource_tenant_id: TenantId,
) -> None:
    """Verify that user and resource belong to the same tenant.

    Per AD-002 and Section 10.3: cross-tenant access is rejected.
    """
    if user_tenant_id != resource_tenant_id:
        audit(
            event_type=AuditEventType.CROSS_TENANT_ACCESS_BLOCKED,
            tenant_id=user_tenant_id,
            detail=(
                f"Cross-tenant access blocked: user={user_tenant_id} resource={resource_tenant_id}"
            ),
        )
        raise PermissionError(
            f"Cross-tenant access blocked: user tenant {user_tenant_id} "
            f"cannot access resource in tenant {resource_tenant_id}"
        )


def create_user_in_tenant(
    *,
    tenant_id: TenantId,
    email: str,
    role: UserRole,
    actor: User,
) -> User:
    """Create a user within a tenant, verifying tenant isolation.

    Per AD-010: the actor must be in the same tenant and have
    sufficient privilege to create the target role.
    """
    check_tenant_access(actor, tenant_id)

    if not can_create_user(actor, role):
        raise InsufficientPrivilegeError(
            f"Actor {actor.role.value} cannot create user with role {role.value}"
        )

    return register_user(
        tenant_id=tenant_id,
        email=email,
        password="temp-change-me",  # Will be set by user on first login
        role=role.value,
    )


def suspend_user(
    *,
    tenant_id: TenantId,
    target_user_id: UserId,
    actor: User,
) -> None:
    """Suspend a user within a tenant.

    Per AD-010: actor must have higher privilege than target.
    """
    check_tenant_access(actor, tenant_id)

    store = get_store()
    target = store.get_user(target_user_id)
    if target is None:
        raise ValueError(f"User not found: {target_user_id}")

    if not can_suspend_user(actor, target):
        raise PermissionError(f"Actor {actor.role.value} cannot suspend user {target.role.value}")

    target.is_active = False
    store.update_user(target)

    audit(
        event_type=AuditEventType.USER_SUSPENDED,
        tenant_id=tenant_id,
        actor_user_id=actor.user_id,
        detail=f"User suspended: {target.email}",
    )


def reactivate_user(
    *,
    tenant_id: TenantId,
    target_user_id: UserId,
    actor: User,
) -> None:
    """Reactivate a previously suspended user."""
    check_tenant_access(actor, tenant_id)

    store = get_store()
    target = store.get_user(target_user_id)
    if target is None:
        raise ValueError(f"User not found: {target_user_id}")

    if not can_suspend_user(actor, target):
        raise PermissionError(
            f"Actor {actor.role.value} cannot reactivate user {target.role.value}"
        )

    target.is_active = True
    target.failed_login_count = 0
    target.locked_until = None
    store.update_user(target)

    audit(
        event_type=AuditEventType.USER_REACTIVATED,
        tenant_id=tenant_id,
        actor_user_id=actor.user_id,
        detail=f"User reactivated: {target.email}",
    )


def get_users_in_tenant(tenant_id: TenantId, actor: User) -> list[User]:
    """List all users in a tenant (tenant-scoped)."""
    check_tenant_access(actor, tenant_id)
    return get_store().get_users_by_tenant(tenant_id)
