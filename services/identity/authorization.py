"""Authorization policy engine for Kian Trading Intelligence.

Architecture Decisions: AD-010 (Zero-Trust), AD-020 (Policy-Governed
Agent Orchestration), AD-026 (Step-Up Authorization).

Authorization is based on user roles (least-privilege) and session
step-up status. Sensitive operations require step-up authentication.

Per AD-010: least privilege — a VIEWER cannot trade, a TRADER cannot
configure risk policy, etc.
Per AD-026: step-up authentication for sensitive operations.
"""

from __future__ import annotations

from contracts.identity import (
    ROLE_PRIVILEGE_LEVEL,
    AuthSession,
    SessionStatus,
    TenantId,
    User,
    UserRole,
    can_manage_role,
)
from services.identity.session import check_step_up


class AuthorizationError(Exception):
    """Raised when an action is not authorized."""


class TenantIsolationError(AuthorizationError):
    """Raised when cross-tenant access is attempted."""


class InsufficientPrivilegeError(AuthorizationError):
    """Raised when a user lacks the required role."""


class StepUpRequiredError(AuthorizationError):
    """Raised when step-up authentication is required."""


# ── Permission definitions ──
# Each permission maps to the minimum role required.


class Permission:
    """Permission constants for authorization checks."""

    VIEW_DASHBOARD = "view_dashboard"
    VIEW_TRADES = "view_trades"
    CREATE_TRADE = "create_trade"
    CANCEL_TRADE = "cancel_trade"
    VIEW_RISK = "view_risk"
    MANAGE_RISK_POLICY = "manage_risk_policy"
    VIEW_USERS = "view_users"
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_CREDENTIALS = "manage_credentials"
    ACCESS_CREDENTIAL_VAULT = "access_credential_vault"
    MANAGE_TENANT = "manage_tenant"


# Minimum role required for each permission
PERMISSION_MIN_ROLE: dict[str, UserRole] = {
    Permission.VIEW_DASHBOARD: UserRole.VIEWER,
    Permission.VIEW_TRADES: UserRole.VIEWER,
    Permission.CREATE_TRADE: UserRole.TRADER,
    Permission.CANCEL_TRADE: UserRole.TRADER,
    Permission.VIEW_RISK: UserRole.RISK_MANAGER,
    Permission.MANAGE_RISK_POLICY: UserRole.RISK_MANAGER,
    Permission.VIEW_USERS: UserRole.ADMIN,
    Permission.MANAGE_USERS: UserRole.ADMIN,
    Permission.VIEW_AUDIT_LOGS: UserRole.ADMIN,
    Permission.MANAGE_CREDENTIALS: UserRole.ADMIN,
    Permission.ACCESS_CREDENTIAL_VAULT: UserRole.ADMIN,
    Permission.MANAGE_TENANT: UserRole.OWNER,
}

# Permissions that require step-up authentication
STEP_UP_REQUIRED_PERMISSIONS: frozenset[str] = frozenset(
    {
        Permission.MANAGE_RISK_POLICY,
        Permission.MANAGE_USERS,
        Permission.ACCESS_CREDENTIAL_VAULT,
        Permission.MANAGE_CREDENTIALS,
        Permission.MANAGE_TENANT,
    }
)


def check_tenant_access(user: User, target_tenant_id: TenantId) -> None:
    """Verify that a user belongs to the target tenant.

    Per AD-002 and AD-010: cross-tenant access is rejected.
    """
    if user.tenant_id != target_tenant_id:
        raise TenantIsolationError(
            f"Cross-tenant access blocked: user tenant {user.tenant_id} "
            f"!= target tenant {target_tenant_id}"
        )


def check_permission(
    user: User,
    session: AuthSession,
    permission: str,
    target_tenant_id: TenantId | None = None,
) -> None:
    """Check if a user+session is authorized for a permission.

    Per AD-010: role-based access control (least privilege).
    Per AD-026: step-up for sensitive operations.

    Args:
        user: The authenticated user.
        session: The user's current session.
        permission: The permission to check.
        target_tenant_id: The tenant being accessed (for tenant isolation).

    Raises:
        TenantIsolationError: Cross-tenant access.
        InsufficientPrivilegeError: Role insufficient.
        StepUpRequiredError: Step-up authentication required.
        ValueError: Unknown permission.
    """
    if permission not in PERMISSION_MIN_ROLE:
        raise ValueError(f"Unknown permission: {permission}")

    # Tenant isolation check
    if target_tenant_id is not None:
        check_tenant_access(user, target_tenant_id)
    else:
        # Always check against user's own tenant
        check_tenant_access(user, user.tenant_id)

    # Session must be active
    if session.status == SessionStatus.REVOKED:
        raise AuthorizationError("Session has been revoked")
    if session.status == SessionStatus.EXPIRED or session.is_expired:
        raise AuthorizationError("Session has expired")

    # Role check
    required_role = PERMISSION_MIN_ROLE[permission]
    user_level = ROLE_PRIVILEGE_LEVEL[user.role]
    required_level = ROLE_PRIVILEGE_LEVEL[required_role]
    if user_level < required_level:
        raise InsufficientPrivilegeError(
            f"Insufficient privilege: {user.role.value} requires {required_role.value} "
            f"for permission '{permission}'"
        )

    # Step-up check for sensitive operations
    if permission in STEP_UP_REQUIRED_PERMISSIONS and not check_step_up(session):
        raise StepUpRequiredError(f"Step-up authentication required for permission '{permission}'")


def can_create_user(actor: User, target_role: UserRole) -> bool:
    """Check if actor can create a user with the given role.

    Per AD-010: an actor can only create users with strictly lower privilege.
    """
    return can_manage_role(actor.role, target_role)


def can_suspend_user(actor: User, target: User) -> bool:
    """Check if actor can suspend the target user.

    Per AD-010: actor must have higher privilege and be in the same tenant.
    """
    if actor.tenant_id != target.tenant_id:
        return False
    return can_manage_role(actor.role, target.role)
