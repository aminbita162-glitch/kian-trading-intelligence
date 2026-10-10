"""Authentication service for Kian Trading Intelligence.

Architecture Decisions: AD-010 (Zero-Trust), AD-026 (Step-Up Authorization).

Per AD-010: strong authentication, revocable sessions, least privilege.
Per AD-026: tenant-scoped identity, MFA, step-up for sensitive operations.

Security invariants:
- Passwords are never stored in plaintext (hashed with salt).
- Failed login attempts lock the account after MAX_FAILED_ATTEMPTS.
- Sessions are revocable and expire automatically.
- Cross-tenant authentication is rejected.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from contracts.identity import (
    AuditEventType,
    AuthSession,
    Device,
    DeviceStatus,
    TenantId,
    User,
    UserId,
    UserRole,
)
from services.identity.audit import audit
from services.identity.database import get_store
from services.identity.session import create_session, revoke_session

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=30)


def _hash_password(password: str, salt: str) -> str:
    """Hash a password with a salt using PBKDF2-HMAC-SHA256.

    Per AD-010: never store plaintext passwords.
    """
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()


def generate_salt() -> str:
    """Generate a cryptographically secure salt."""
    return secrets.token_hex(16)


class AuthenticationError(Exception):
    """Raised when authentication fails."""


class AccountLockedError(AuthenticationError):
    """Raised when an account is locked due to failed attempts."""


class AccountInactiveError(AuthenticationError):
    """Raised when an account is inactive."""


class MFARequiredError(AuthenticationError):
    """Raised when MFA is required for login."""


class MFAVerificationError(AuthenticationError):
    """Raised when MFA verification fails."""


class TenantMismatchError(AuthenticationError):
    """Raised when a user attempts to authenticate under the wrong tenant."""

    def __init__(self, msg: str = "Tenant mismatch: user does not belong to this tenant") -> None:
        super().__init__(msg)


# ── Password store (in-memory; would be in DB in production) ──
_passwords: dict[str, str] = {}  # user_id -> hashed_password
_salts: dict[str, str] = {}  # user_id -> salt


def set_password(user_id: UserId, password: str) -> None:
    """Set a user's password (hashed with salt)."""
    salt = generate_salt()
    _salts[str(user_id)] = salt
    _passwords[str(user_id)] = _hash_password(password, salt)


def verify_password(user_id: UserId, password: str) -> bool:
    """Verify a password against the stored hash."""
    uid = str(user_id)
    if uid not in _passwords or uid not in _salts:
        return False
    return hmac.compare_digest(_hash_password(password, _salts[uid]), _passwords[uid])


def reset_passwords() -> None:
    """Clear all stored passwords. For testing only."""
    _passwords.clear()
    _salts.clear()


def register_user(
    *,
    tenant_id: TenantId,
    email: str,
    password: str,
    role: str = "viewer",
) -> User:
    """Register a new user with password authentication.

    The user is created within the given tenant. The tenant must
    already exist (tenant isolation per AD-002).
    """
    store = get_store()
    tenant = store.get_tenant(tenant_id)
    if tenant is None or not tenant.is_active:
        raise AuthenticationError("Tenant not found or inactive")

    existing = store.get_user_by_email(tenant_id, email)
    if existing is not None:
        raise AuthenticationError(f"User with email {email} already exists in tenant")

    user_role = UserRole(role)
    user = User.create(tenant_id=tenant_id, email=email, role=user_role)
    store.create_user(user)
    set_password(user.user_id, password)

    audit(
        event_type=AuditEventType.USER_CREATED,
        tenant_id=tenant_id,
        actor_user_id=user.user_id,
        detail=f"User created: {email}",
    )

    return user


def _handle_device(
    tenant_id: TenantId,
    user: User,
    device_fingerprint: str,
) -> Device:
    """Handle device registration/trust for authentication.

    Returns the device record (may be new, pending, or existing).
    Raises AuthenticationError if the device is blocked.
    """
    store = get_store()
    devices = store.get_devices_by_user(tenant_id, user.user_id)
    existing_device = next(
        (d for d in devices if d.fingerprint == device_fingerprint),
        None,
    )
    if existing_device is not None:
        if existing_device.status == DeviceStatus.BLOCKED:
            raise AuthenticationError("Device is blocked")
        existing_device.last_seen = datetime.now(UTC)
        store.update_device(existing_device)
        return existing_device

    new_device = Device.create(
        tenant_id=tenant_id,
        user_id=user.user_id,
        fingerprint=device_fingerprint,
    )
    new_device.status = DeviceStatus.PENDING
    store.create_device(new_device)
    return new_device


def _handle_mfa(
    tenant_id: TenantId,
    user: User,
    session: AuthSession,
    email: str,
) -> None:
    """Handle MFA challenge for authenticated users."""
    if not user.mfa_enabled:
        get_store().update_session(session)
        return
    session.require_step_up()
    get_store().update_session(session)
    audit(
        event_type=AuditEventType.MFA_CHALLENGED,
        tenant_id=tenant_id,
        actor_user_id=user.user_id,
        detail=f"MFA challenge issued: {email}",
    )


def authenticate(
    *,
    tenant_id: TenantId,
    email: str,
    password: str,
    device_fingerprint: str | None = None,
) -> tuple[User, AuthSession]:
    """Authenticate a user with email and password.

    Returns (user, session) on success.
    Raises AuthenticationError on failure.

    Per AD-010: failed attempts are tracked and accounts are locked.
    Per AD-026: sessions are revocable and tenant-scoped.
    """
    store = get_store()
    user = store.get_user_by_email(tenant_id, email)

    if user is None:
        audit(
            event_type=AuditEventType.LOGIN_FAILED,
            tenant_id=tenant_id,
            detail=f"Login failed (user not found): {email}",
        )
        raise AuthenticationError("Invalid credentials")

    if user.tenant_id != tenant_id:
        audit(
            event_type=AuditEventType.CROSS_TENANT_ACCESS_BLOCKED,
            tenant_id=tenant_id,
            actor_user_id=user.user_id,
            detail="Cross-tenant authentication blocked",
        )
        raise TenantMismatchError()

    if not user.is_active:
        audit(
            event_type=AuditEventType.LOGIN_FAILED,
            tenant_id=tenant_id,
            actor_user_id=user.user_id,
            detail=f"Login failed (inactive account): {email}",
        )
        raise AccountInactiveError("Account is inactive")

    if user.is_locked:
        audit(
            event_type=AuditEventType.LOGIN_FAILED,
            tenant_id=tenant_id,
            actor_user_id=user.user_id,
            detail=f"Login failed (locked account): {email}",
        )
        raise AccountLockedError("Account is locked due to failed attempts")

    if not verify_password(user.user_id, password):
        _record_failed_login(tenant_id, user, email)
        raise AuthenticationError("Invalid credentials")

    # Success — reset failed attempts
    user.failed_login_count = 0
    user.locked_until = None
    store.update_user(user)

    # Handle device
    device: Device | None = None
    if device_fingerprint is not None:
        device = _handle_device(tenant_id, user, device_fingerprint)

    # Create session
    session = create_session(
        tenant_id=tenant_id,
        user_id=user.user_id,
        device_id=device.device_id if device else None,
    )

    _handle_mfa(tenant_id, user, session, email)

    audit(
        event_type=AuditEventType.LOGIN_SUCCESS,
        tenant_id=tenant_id,
        actor_user_id=user.user_id,
        detail=f"Login successful: {email}",
    )

    return user, session


def _record_failed_login(
    tenant_id: TenantId,
    user: User,
    email: str,
) -> None:
    """Record a failed login attempt and lock account if needed."""
    store = get_store()
    user.failed_login_count += 1
    if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.now(UTC) + LOCK_DURATION
        audit(
            event_type=AuditEventType.LOGIN_FAILED,
            tenant_id=tenant_id,
            actor_user_id=user.user_id,
            detail=f"Account locked after {MAX_FAILED_ATTEMPTS} failed attempts: {email}",
        )
    else:
        audit(
            event_type=AuditEventType.LOGIN_FAILED,
            tenant_id=tenant_id,
            actor_user_id=user.user_id,
            detail=f"Login failed (wrong password): {email}",
        )
    store.update_user(user)


def logout(session: AuthSession) -> None:
    """Revoke a session and audit the logout."""
    revoke_session(str(session.session_id))
    audit(
        event_type=AuditEventType.LOGOUT,
        tenant_id=session.tenant_id,
        actor_user_id=session.user_id,
        detail="User logged out",
    )
