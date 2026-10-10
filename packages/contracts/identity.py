"""Identity and multi-tenant security contracts for Kian Trading Intelligence.

Architecture Decisions: AD-002 (Multi-Tenant Foundation), AD-008 (User Onboarding),
AD-010 (Zero-Trust Security), AD-026 (Centralized Identity and Step-Up Authorization).

Phase 02 deliverables: tenant and user models, profile management,
MFA contracts, session and device controls, security audit events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum as NativeStrEnum
from uuid import UUID, uuid4


class UserRole(NativeStrEnum):
    """User roles per AD-010 (Zero-Trust) and AD-026 (Step-Up Authorization).

    Roles follow least-privilege: a VIEWER cannot trade, a TRADER cannot
    configure risk policy, an ADMIN manages tenant configuration, and
    only OWNER holds full tenant authority.
    """

    VIEWER = "viewer"
    TRADER = "trader"
    RISK_MANAGER = "risk_manager"
    ADMIN = "admin"
    OWNER = "owner"


class MFAMethod(NativeStrEnum):
    """MFA delivery methods per AD-010 and AD-026."""

    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"
    HARDWARE_KEY = "hardware_key"


class SessionStatus(NativeStrEnum):
    """Authentication session lifecycle status."""

    ACTIVE = "active"
    STEP_UP_REQUIRED = "step_up_required"
    EXPIRED = "expired"
    REVOKED = "revoked"
    LOCKED = "locked"


class DeviceStatus(NativeStrEnum):
    """Trusted device lifecycle status."""

    PENDING = "pending"
    TRUSTED = "trusted"
    REVOKED = "revoked"
    BLOCKED = "blocked"


class AuditEventType(NativeStrEnum):
    """Security audit event types per AD-022 (Observability and Audit).

    Events are tamper-evident and access-controlled (Section 13).
    """

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"
    MFA_CHALLENGED = "mfa_challenged"
    MFA_VERIFIED = "mfa_verified"
    MFA_FAILED = "mfa_failed"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    STEP_UP_GRANTED = "step_up_granted"
    STEP_UP_DENIED = "step_up_denied"
    DEVICE_TRUSTED = "device_trusted"
    DEVICE_REVOKED = "device_revoked"
    DEVICE_BLOCKED = "device_blocked"
    CREDENTIAL_STORED = "credential_stored"
    CREDENTIAL_ACCESSED = "credential_accessed"
    CREDENTIAL_ROTATED = "credential_rotated"
    CREDENTIAL_REVOKED = "credential_revoked"
    CROSS_TENANT_ACCESS_BLOCKED = "cross_tenant_access_blocked"
    PRIVILEGE_ESCALATION_BLOCKED = "privilege_escalation_blocked"
    TENANT_CREATED = "tenant_created"
    USER_CREATED = "user_created"
    USER_SUSPENDED = "user_suspended"
    USER_REACTIVATED = "user_reactivated"


class CredentialType(NativeStrEnum):
    """Credential vault entry types per AD-019 (Non-Custodial Credential Vault)."""

    EXCHANGE_API_KEY = "exchange_api_key"
    EXCHANGE_API_SECRET = "exchange_api_secret"
    WALLET_PRIVATE_KEY = "wallet_private_key"
    OTHER = "other"


@dataclass(frozen=True)
class TenantId:
    """Stable identity for a tenant.

    Per AD-002: tenant isolation is designed from inception.
    """

    value: UUID

    @classmethod
    def generate(cls) -> TenantId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class UserId:
    """Stable identity for a user."""

    value: UUID

    @classmethod
    def generate(cls) -> UserId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class Tenant:
    """Multi-tenant organization per AD-002.

    A tenant is the isolation boundary: all users, profiles, sessions,
    and credentials belong to exactly one tenant. Cross-tenant access
    is tested and rejected (Section 10.3).
    """

    tenant_id: TenantId
    name: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, *, name: str) -> Tenant:
        return cls(tenant_id=TenantId.generate(), name=name)


@dataclass
class User:
    """User model per AD-008 (User Onboarding) and AD-010 (Zero-Trust).

    Attributes:
        user_id: Stable unique identifier.
        tenant_id: Owning tenant (isolation boundary).
        email: Login identifier.
        role: Authorization role (least-privilege).
        is_active: Whether the user can authenticate.
        mfa_enabled: Whether MFA is required for this user.
        mfa_method: Configured MFA method (if any).
        failed_login_count: Consecutive failed login attempts.
        locked_until: Timestamp until which login is locked.
        created_at: Account creation timestamp.
    """

    user_id: UserId
    tenant_id: TenantId
    email: str
    role: UserRole
    is_active: bool = True
    mfa_enabled: bool = False
    mfa_method: MFAMethod | None = None
    mfa_secret: str | None = None
    failed_login_count: int = 0
    locked_until: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(  # noqa: PLR0913
        cls,
        *,
        tenant_id: TenantId,
        email: str,
        role: UserRole,
    ) -> User:
        return cls(
            user_id=UserId.generate(),
            tenant_id=tenant_id,
            email=email,
            role=role,
        )

    @property
    def is_locked(self) -> bool:
        """True if the account is locked due to failed login attempts."""
        if self.locked_until is None:
            return False
        return datetime.now(UTC) < self.locked_until


@dataclass
class TradingProfile:
    """User trading profile per AD-008.

    User-entered profile information is not equivalent to provider KYC.
    """

    profile_id: UUID
    tenant_id: TenantId
    user_id: UserId
    display_name: str
    timezone: str = "UTC"
    language: str = "en"
    base_currency: str = "USDT"
    risk_tolerance: str = "moderate"
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        user_id: UserId,
        display_name: str,
    ) -> TradingProfile:
        return cls(
            profile_id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            display_name=display_name,
        )


@dataclass
class Device:
    """Trusted device per AD-010 (device controls) and AD-026.

    A device must be explicitly trusted before step-up authorization
    can be skipped for it.
    """

    device_id: UUID
    tenant_id: TenantId
    user_id: UserId
    fingerprint: str
    status: DeviceStatus = DeviceStatus.PENDING
    trusted_at: datetime | None = None
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        user_id: UserId,
        fingerprint: str,
    ) -> Device:
        return cls(
            device_id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            fingerprint=fingerprint,
        )

    def trust(self) -> None:
        self.status = DeviceStatus.TRUSTED
        self.trusted_at = datetime.now(UTC)

    def revoke(self) -> None:
        self.status = DeviceStatus.REVOKED
        self.trusted_at = None

    def block(self) -> None:
        self.status = DeviceStatus.BLOCKED
        self.trusted_at = None


@dataclass
class AuthSession:
    """Authentication session per AD-026 (Centralized Identity).

    Sessions are revocable, tenant-scoped, and may require step-up
    authentication for sensitive operations.
    """

    session_id: UUID
    tenant_id: TenantId
    user_id: UserId
    device_id: UUID | None
    status: SessionStatus
    step_up_until: datetime | None
    expires_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        *,
        tenant_id: TenantId,
        user_id: UserId,
        device_id: UUID | None = None,
        session_duration: timedelta | None = None,
    ) -> AuthSession:
        duration = session_duration or timedelta(hours=1)
        return cls(
            session_id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            device_id=device_id,
            status=SessionStatus.ACTIVE,
            step_up_until=None,
            expires_at=datetime.now(UTC) + duration,
        )

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at

    @property
    def has_step_up(self) -> bool:
        """True if a valid step-up authorization is currently active."""
        if self.step_up_until is None:
            return False
        return datetime.now(UTC) < self.step_up_until

    def require_step_up(self, step_up_duration: timedelta | None = None) -> None:
        """Mark session as requiring step-up authentication."""
        self.status = SessionStatus.STEP_UP_REQUIRED
        self.step_up_until = None

    def grant_step_up(self, step_up_duration: timedelta | None = None) -> None:
        """Grant step-up authorization for a limited time."""
        duration = step_up_duration or timedelta(minutes=15)
        self.step_up_until = datetime.now(UTC) + duration
        self.status = SessionStatus.ACTIVE

    def touch(self) -> None:
        self.last_activity = datetime.now(UTC)

    def revoke(self) -> None:
        self.status = SessionStatus.REVOKED


@dataclass(frozen=True)
class AuditEventId:
    """Stable identity for a security audit event."""

    value: UUID

    @classmethod
    def generate(cls) -> AuditEventId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class AuditEvent:
    """Security audit event per AD-022 (Observability and Audit).

    Audit evidence must be tamper-evident and access-controlled.
    Sensitive values must be redacted (Section 13).
    """

    event_id: AuditEventId
    event_type: AuditEventType
    tenant_id: TenantId
    actor_user_id: UserId | None
    timestamp: datetime
    detail: str
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        event_type: AuditEventType,
        tenant_id: TenantId,
        actor_user_id: UserId | None = None,
        detail: str = "",
        metadata: dict[str, str] | None = None,
    ) -> AuditEvent:
        return cls(
            event_id=AuditEventId.generate(),
            event_type=event_type,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            timestamp=datetime.now(UTC),
            detail=detail,
            metadata=metadata or {},
        )


# ── Privilege Hierarchy ──
# Used for privilege-escalation checks (AD-010).
ROLE_PRIVILEGE_LEVEL: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.TRADER: 1,
    UserRole.RISK_MANAGER: 2,
    UserRole.ADMIN: 3,
    UserRole.OWNER: 4,
}


def can_manage_role(actor_role: UserRole, target_role: UserRole) -> bool:
    """Check if actor can manage (create/modify/suspend) a user with target_role.

    Per AD-010 (least privilege): an actor can only manage users with
    strictly lower privilege than themselves. An OWNER can manage all
    except other OWNERs (same-level is not manageable).
    """
    return ROLE_PRIVILEGE_LEVEL[actor_role] > ROLE_PRIVILEGE_LEVEL[target_role]
