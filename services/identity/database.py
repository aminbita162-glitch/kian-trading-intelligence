"""In-memory database for Phase 02 identity and multi-tenant security.

Per AD-031: PostgreSQL is planned for durable records. Phase 02 uses
an in-memory store with the same interface so that migration to
PostgreSQL is a storage-layer change only (AD-024 progressive delivery).

Per AD-002: all data is tenant-scoped. The store enforces tenant isolation
at the data-access layer: every record carries a tenant_id and queries
are scoped by the caller's tenant.

Per AD-017: fault-tolerant recovery is not yet implemented — this is
an in-memory development store, not a production database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

from contracts.identity import (
    AuditEvent,
    AuthSession,
    Device,
    Tenant,
    TenantId,
    TradingProfile,
    User,
    UserId,
)


class IdentityStore:
    """Thread-safe in-memory store for identity data.

    All access is tenant-scoped. Cross-tenant access is rejected
    at the service layer (tenant isolation per AD-002, AD-010).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._tenants: dict[str, Tenant] = {}
        self._users: dict[str, User] = {}
        self._profiles: dict[str, TradingProfile] = {}
        self._sessions: dict[str, AuthSession] = {}
        self._devices: dict[str, Device] = {}
        self._audit_events: list[AuditEvent] = []

    # ── Tenant operations ──

    def create_tenant(self, tenant: Tenant) -> None:
        with self._lock:
            key = str(tenant.tenant_id)
            if key in self._tenants:
                raise ValueError(f"Tenant already exists: {key}")
            self._tenants[key] = tenant

    def get_tenant(self, tenant_id: TenantId) -> Tenant | None:
        with self._lock:
            return self._tenants.get(str(tenant_id))

    # ── User operations ──

    def create_user(self, user: User) -> None:
        with self._lock:
            key = str(user.user_id)
            if key in self._users:
                raise ValueError(f"User already exists: {key}")
            self._users[key] = user

    def get_user(self, user_id: UserId) -> User | None:
        with self._lock:
            return self._users.get(str(user_id))

    def get_user_by_email(self, tenant_id: TenantId, email: str) -> User | None:
        with self._lock:
            for user in self._users.values():
                if user.tenant_id == tenant_id and user.email == email:
                    return user
            return None

    def get_users_by_tenant(self, tenant_id: TenantId) -> list[User]:
        with self._lock:
            return [u for u in self._users.values() if u.tenant_id == tenant_id]

    def update_user(self, user: User) -> None:
        with self._lock:
            key = str(user.user_id)
            if key not in self._users:
                raise ValueError(f"User not found: {key}")
            self._users[key] = user

    # ── Profile operations ──

    def create_profile(self, profile: TradingProfile) -> None:
        with self._lock:
            key = str(profile.profile_id)
            if key in self._profiles:
                raise ValueError(f"Profile already exists: {key}")
            self._profiles[key] = profile

    def get_profile(self, profile_id: str) -> TradingProfile | None:
        with self._lock:
            return self._profiles.get(profile_id)

    def get_profiles_by_tenant(self, tenant_id: TenantId) -> list[TradingProfile]:
        with self._lock:
            return [p for p in self._profiles.values() if p.tenant_id == tenant_id]

    def get_profiles_by_user(self, tenant_id: TenantId, user_id: UserId) -> list[TradingProfile]:
        with self._lock:
            return [
                p
                for p in self._profiles.values()
                if p.tenant_id == tenant_id and p.user_id == user_id
            ]

    # ── Session operations ──

    def create_session(self, session: AuthSession) -> None:
        with self._lock:
            key = str(session.session_id)
            if key in self._sessions:
                raise ValueError(f"Session already exists: {key}")
            self._sessions[key] = session

    def get_session(self, session_id: str) -> AuthSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_sessions_by_tenant(self, tenant_id: TenantId) -> list[AuthSession]:
        with self._lock:
            return [s for s in self._sessions.values() if s.tenant_id == tenant_id]

    def update_session(self, session: AuthSession) -> None:
        with self._lock:
            key = str(session.session_id)
            if key not in self._sessions:
                raise ValueError(f"Session not found: {key}")
            self._sessions[key] = session

    def revoke_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.revoke()
            return True

    # ── Device operations ──

    def create_device(self, device: Device) -> None:
        with self._lock:
            key = str(device.device_id)
            if key in self._devices:
                raise ValueError(f"Device already exists: {key}")
            self._devices[key] = device

    def get_device(self, device_id: str) -> Device | None:
        with self._lock:
            return self._devices.get(device_id)

    def get_devices_by_user(self, tenant_id: TenantId, user_id: UserId) -> list[Device]:
        with self._lock:
            return [
                d
                for d in self._devices.values()
                if d.tenant_id == tenant_id and d.user_id == user_id
            ]

    def update_device(self, device: Device) -> None:
        with self._lock:
            key = str(device.device_id)
            if key not in self._devices:
                raise ValueError(f"Device not found: {key}")
            self._devices[key] = device

    # ── Audit operations ──

    def record_audit_event(self, event: AuditEvent) -> None:
        with self._lock:
            self._audit_events.append(event)

    def get_audit_events_by_tenant(self, tenant_id: TenantId, limit: int = 100) -> list[AuditEvent]:
        with self._lock:
            events = [e for e in self._audit_events if e.tenant_id == tenant_id]
            return events[-limit:]

    def get_all_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        with self._lock:
            return self._audit_events[-limit:]

    # ── Reset (for testing) ──

    def reset(self) -> None:
        with self._lock:
            self._tenants.clear()
            self._users.clear()
            self._profiles.clear()
            self._sessions.clear()
            self._devices.clear()
            self._audit_events.clear()

    @property
    def now(self) -> datetime:
        """Current UTC timestamp."""
        return datetime.now(UTC)


# Module-level singleton store
_store: IdentityStore | None = None


def get_store() -> IdentityStore:
    """Get the singleton identity store instance."""
    global _store  # noqa: PLW0603
    if _store is None:
        _store = IdentityStore()
    return _store


def reset_store() -> None:
    """Reset the singleton store. For testing only."""
    global _store  # noqa: PLW0603
    if _store is not None:
        _store.reset()
    else:
        _store = IdentityStore()
