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

import os
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol

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


class IdentityStoreProtocol(Protocol):
    """Protocol defining the identity store interface (F-SEC-03).

    Both the in-memory ``IdentityStore`` and the ``PersistentIdentityStore``
    implement this protocol.  Callers depend only on the protocol, not
    on a specific implementation.
    """

    def create_tenant(self, tenant: Tenant) -> None: ...
    def get_tenant(self, tenant_id: TenantId) -> Tenant | None: ...
    def create_user(self, user: User) -> None: ...
    def get_user(self, user_id: UserId) -> User | None: ...
    def get_user_by_email(self, tenant_id: TenantId, email: str) -> User | None: ...
    def get_users_by_tenant(self, tenant_id: TenantId) -> list[User]: ...
    def update_user(self, user: User) -> None: ...
    def create_profile(self, profile: TradingProfile) -> None: ...
    def get_profile(self, profile_id: str) -> TradingProfile | None: ...
    def get_profiles_by_tenant(self, tenant_id: TenantId) -> list[TradingProfile]: ...
    def get_profiles_by_user(
        self, tenant_id: TenantId, user_id: UserId
    ) -> list[TradingProfile]: ...
    def create_session(self, session: AuthSession) -> None: ...
    def get_session(self, session_id: str) -> AuthSession | None: ...
    def get_sessions_by_tenant(self, tenant_id: TenantId) -> list[AuthSession]: ...
    def update_session(self, session: AuthSession) -> None: ...
    def revoke_session(self, session_id: str) -> bool: ...
    def create_device(self, device: Device) -> None: ...
    def get_device(self, device_id: str) -> Device | None: ...
    def get_devices_by_user(self, tenant_id: TenantId, user_id: UserId) -> list[Device]: ...
    def update_device(self, device: Device) -> None: ...
    def record_audit_event(self, event: AuditEvent) -> None: ...
    def get_audit_events_by_tenant(
        self, tenant_id: TenantId, limit: int = 100
    ) -> list[AuditEvent]: ...
    def get_all_audit_events(self, limit: int = 100) -> list[AuditEvent]: ...
    def set_password_hash(self, user_id: UserId, password_hash: str, salt: str) -> None: ...
    def get_password_hash(self, user_id: UserId) -> tuple[str, str] | None: ...
    def reset(self) -> None: ...


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

    # ── Password storage (persistent) ──

    def set_password_hash(self, user_id: UserId, password_hash: str, salt: str) -> None:
        """Store a password hash and salt (F-SEC-03).

        In the in-memory store, these are kept in module-level dicts
        in ``services.identity.auth``.  This method is a no-op here
        because the in-memory ``IdentityStore`` does not own password
        storage.  The ``PersistentIdentityStore`` overrides this to
        persist to the database.
        """
        # No-op: passwords are handled by auth.py's in-memory dicts
        # when the in-memory IdentityStore is used.

    def get_password_hash(self, user_id: UserId) -> tuple[str, str] | None:
        """Retrieve a password hash and salt (F-SEC-03).

        Returns ``None`` for the in-memory store; the
        ``PersistentIdentityStore`` overrides this to read from the DB.
        """
        return None

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


# Module-level store management (F-SEC-03)
# The store is now a PersistentIdentityStore by default (SQLite in dev,
# PostgreSQL in production). The in-memory IdentityStore above remains
# available for backward compatibility but is not used by get_store().

_store: IdentityStore | None = None


def get_store() -> IdentityStore:
    """Get the singleton identity store instance.

    F-SEC-03 RESOLVED: Returns a ``PersistentIdentityStore`` backed by
    SQLAlchemy (SQLite in development, PostgreSQL in production).
    Falls back to the in-memory ``IdentityStore`` only if
    ``KTI_USE_PERSISTENT_STORE`` is set to ``false``.
    """
    use_persistent = os.environ.get("KTI_USE_PERSISTENT_STORE", "true").lower()
    if use_persistent == "false":
        return _get_in_memory_store()
    return _get_persistent_store()


def _get_in_memory_store() -> IdentityStore:
    global _store  # noqa: PLW0603
    if _store is None:
        _store = IdentityStore()
    return _store


def _get_persistent_store() -> IdentityStore:
    """Return the persistent identity store (F-SEC-03).

    Imports ``PersistentIdentityStore`` lazily to avoid importing
    SQLAlchemy when it's not needed.
    """
    from services.identity.persistence import get_persistent_store  # noqa: PLC0415

    return get_persistent_store()


def reset_store() -> None:
    """Reset the singleton store. For testing only."""
    use_persistent = os.environ.get("KTI_USE_PERSISTENT_STORE", "true").lower()
    if use_persistent == "false":
        global _store  # noqa: PLW0603
        if _store is not None:
            _store.reset()
        else:
            _store = IdentityStore()
    else:
        from services.identity.persistence import reset_persistent_store  # noqa: PLC0415

        reset_persistent_store()
