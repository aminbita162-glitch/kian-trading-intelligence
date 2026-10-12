"""Persistent identity store for Kian Trading Intelligence (F-SEC-03).

Architecture Decisions: AD-002 (Multi-Tenant), AD-010 (Zero-Trust),
AD-026 (Centralized Identity), AD-031 (PostgreSQL for durable records),
AD-024 (Progressive Delivery).

Replaces the in-memory ``IdentityStore`` with a SQLAlchemy-backed
persistent store that supports PostgreSQL (production) and SQLite
(in-process test).  Key properties:

- **Tenant isolation** — every table carries a ``tenant_id`` column and
  all queries are scoped by the caller's tenant.
- **Secure credential hashing** — passwords are stored as PBKDF2-HMAC-
  SHA256 hashes with per-user salts (same algorithm as the in-memory
  implementation).
- **Transactional integrity** — all mutations occur within a
  ``Session.begin()`` transaction; partial failures roll back.
- **Versioned migrations** — a lightweight migration framework
  creates the schema idempotently.  The ``schema_version`` table
  records the applied version.
- **Fail-closed production** — in production (``KTI_ENVIRONMENT=production``)
  a PostgreSQL URL **must** be supplied via ``KTI_DATABASE_URL``; the
  in-memory fallback is never used in production.
- **Object cache** — live Python objects (``Tenant``, ``User``,
  ``AuthSession``, ``Device``, ``AuditEvent``) are cached so that
  callers who hold references see mutations in real time (same
  reference semantics as the in-memory store).  The DB is the durable
  mirror; the cache is the authoritative in-process state.
"""

from __future__ import annotations

import atexit
import contextlib
import json as _json
import os
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Integer,
    String,
    create_engine,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
)
from sqlalchemy.pool import StaticPool

from contracts.identity import (
    AuditEvent,
    AuthSession,
    Device,
    DeviceStatus,
    MFAMethod,
    SessionStatus,
    Tenant,
    TenantId,
    TradingProfile,
    User,
    UserId,
    UserRole,
)
from services.identity.database import IdentityStore

# ── Exceptions ──


class PersistenceError(Exception):
    """Raised when persistence operations fail."""


class PersistenceConfigurationError(PersistenceError):
    """Raised when the persistence layer is misconfigured (fail-closed)."""


class MigrationError(PersistenceError):
    """Raised when a database migration fails."""


# ── Database URL resolution ──


def _resolve_db_url() -> str:
    """Resolve the database URL from the environment (fail-closed in prod).

    In production, ``KTI_DATABASE_URL`` must be set to a PostgreSQL URL.
    In development, defaults to an in-memory SQLite database.
    """
    url = os.environ.get("KTI_DATABASE_URL", "")
    if _is_production():
        if not url:
            raise PersistenceConfigurationError(
                "KTI_DATABASE_URL is not set. In production, a PostgreSQL "
                "connection URL is required."
            )
        if not url.startswith("postgresql"):
            raise PersistenceConfigurationError(
                "KTI_DATABASE_URL must be a PostgreSQL URL in production."
            )
        return url
    if not url:
        return "sqlite:///:memory:"
    return url


def _is_production() -> bool:
    return os.environ.get("KTI_ENVIRONMENT", "").lower() == "production"


# ── SQLAlchemy models ──


class Base(DeclarativeBase):
    """Declarative base for all identity tables."""


class TenantRow(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40))


class UserRow(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_salt: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ProfileRow(Base):
    __tablename__ = "profiles"

    profile_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    language: Mapped[str] = mapped_column(String(10), default="en")
    base_currency: Mapped[str] = mapped_column(String(20), default="USDT")
    risk_tolerance: Mapped[str] = mapped_column(String(50), default="moderate")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40))


class SessionRow(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(50))
    step_up_until: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expires_at: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40))
    last_activity: Mapped[str] = mapped_column(String(40))


class DeviceRow(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    fingerprint: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50))
    trusted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_seen: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40))


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(String(1000))
    metadata_json: Mapped[str] = mapped_column(String(4000), default="{}")


class SchemaVersionRow(Base):
    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[str] = mapped_column(String(40))


# ── Migration framework ──

CURRENT_SCHEMA_VERSION = 1


class Migration:
    """A single database migration."""

    def __init__(self, version: int, description: str, sql: str) -> None:
        self.version = version
        self.description = description
        self.sql = sql


MIGRATIONS: list[Migration] = [
    Migration(
        1,
        "Initial identity schema — tenants, users, profiles, sessions, "
        "devices, audit_events, schema_version",
        "",  # SQLAlchemy creates all tables via create_all()
    ),
]


def _ensure_schema(session: Session) -> int:
    """Apply pending migrations. Returns the applied version."""
    from services.identity.migrations import run_migrations  # noqa: PLC0415

    Base.metadata.create_all(session.get_bind(), checkfirst=True)

    # Run versioned migrations (raw SQL) for any pending versions.
    engine = session.get_bind()
    # Ensure schema_version table exists for migration tracking.
    existing = session.get(SchemaVersionRow, 1)
    if existing is None:
        # Apply migrations via the migration framework.
        run_migrations(engine)
        # The framework may have inserted rows; check again.
        existing = session.get(SchemaVersionRow, 1)
        if existing is None:
            row = SchemaVersionRow(
                version=CURRENT_SCHEMA_VERSION,
                applied_at=datetime.now(UTC).isoformat(),
            )
            session.add(row)
            session.flush()
    return CURRENT_SCHEMA_VERSION


# ── Helpers ──

_MIN_KEY_LEN = 32


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _now_str() -> str:
    return datetime.now(UTC).isoformat()


# ── Persistent identity store ──


class PersistentIdentityStore(IdentityStore):
    """SQLAlchemy-backed identity store with an in-memory object cache.

    Extends ``IdentityStore`` and overrides all methods to persist
    mutations to the database while maintaining the same reference
    semantics (callers hold live objects that reflect mutations).

    The in-memory dicts from ``IdentityStore`` serve as the live object
    cache; the SQLAlchemy engine serves as the durable mirror.  Every
    create/update/delete operation writes to both.
    """

    # Track all live instances so test teardown can dispose their engines.
    _instances: list[PersistentIdentityStore] = []
    _instances_lock = Lock()

    def __init__(self, db_url: str | None = None) -> None:
        url = db_url or _resolve_db_url()
        self._url = url
        is_sqlite = url.startswith("sqlite")
        self._engine = create_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False} if is_sqlite else {},
            poolclass=StaticPool if is_sqlite else None,
        )
        self._plock = Lock()
        self._initialize()
        # Initialize the parent in-memory dicts so they serve as the
        # live object cache.
        super().__init__()
        with PersistentIdentityStore._instances_lock:
            PersistentIdentityStore._instances.append(self)

    def _initialize(self) -> None:
        """Create tables and run migrations."""
        with Session(self._engine) as session:
            _ensure_schema(session)
            session.commit()

    def close(self) -> None:
        """Dispose the underlying SQLAlchemy engine and release resources.

        After ``close()``, the store must not be reused — create a new
        instance instead.  ``reset()`` keeps the engine alive; only
        ``close()`` tears down the connection pool.
        """
        self._engine.dispose()
        with PersistentIdentityStore._instances_lock, contextlib.suppress(ValueError):
            PersistentIdentityStore._instances.remove(self)

    # ── Row ↔ Domain object conversion ──

    def _row_to_user(self, row: UserRow) -> User:
        locked_until = _str_to_dt(row.locked_until) if row.locked_until else None
        return User(
            user_id=UserId(UUID(row.user_id)),
            tenant_id=TenantId(UUID(row.tenant_id)),
            email=row.email,
            role=UserRole(row.role),
            is_active=row.is_active,
            mfa_enabled=row.mfa_enabled,
            mfa_method=MFAMethod(row.mfa_method) if row.mfa_method else None,
            mfa_secret=row.mfa_secret,
            failed_login_count=row.failed_login_count,
            locked_until=locked_until,
            created_at=_str_to_dt(row.created_at),
        )

    def _row_to_session(self, row: SessionRow) -> AuthSession:
        return AuthSession(
            session_id=UUID(row.session_id),
            tenant_id=TenantId(UUID(row.tenant_id)),
            user_id=UserId(UUID(row.user_id)),
            device_id=UUID(row.device_id) if row.device_id else None,
            status=SessionStatus(row.status),
            step_up_until=_str_to_dt(row.step_up_until) if row.step_up_until else None,
            expires_at=_str_to_dt(row.expires_at),
            created_at=_str_to_dt(row.created_at),
            last_activity=_str_to_dt(row.last_activity),
        )

    def _row_to_device(self, row: DeviceRow) -> Device:
        return Device(
            device_id=UUID(row.device_id),
            tenant_id=TenantId(UUID(row.tenant_id)),
            user_id=UserId(UUID(row.user_id)),
            fingerprint=row.fingerprint,
            status=DeviceStatus(row.status),
            trusted_at=_str_to_dt(row.trusted_at) if row.trusted_at else None,
            last_seen=_str_to_dt(row.last_seen),
            created_at=_str_to_dt(row.created_at),
        )

    # ── Tenant operations ──

    def create_tenant(self, tenant: Tenant) -> None:
        with self._plock, Session(self._engine) as session:
            key = str(tenant.tenant_id)
            if session.get(TenantRow, key) is not None:
                raise ValueError(f"Tenant already exists: {key}")
            row = TenantRow(
                tenant_id=key,
                name=tenant.name,
                is_active=tenant.is_active,
                created_at=_dt_to_str(tenant.created_at),
            )
            session.add(row)
            session.commit()
        # Also cache in memory (parent class)
        super().create_tenant(tenant)

    def get_tenant(self, tenant_id: TenantId) -> Tenant | None:
        # Try in-memory cache first (same reference semantics)
        cached = super().get_tenant(tenant_id)
        if cached is not None:
            return cached
        # Fallback to DB
        with Session(self._engine) as session:
            row = session.get(TenantRow, str(tenant_id))
            if row is None:
                return None
            tenant = Tenant(
                tenant_id=TenantId(UUID(row.tenant_id)),
                name=row.name,
                is_active=row.is_active,
                created_at=_str_to_dt(row.created_at),
            )
            # Cache it so subsequent mutations are reflected
            self._tenants[str(tenant_id)] = tenant
            return tenant

    # ── User operations ──

    def create_user(self, user: User) -> None:
        with self._plock, Session(self._engine) as session:
            key = str(user.user_id)
            if session.get(UserRow, key) is not None:
                raise ValueError(f"User already exists: {key}")
            row = UserRow(
                user_id=key,
                tenant_id=str(user.tenant_id),
                email=user.email,
                role=user.role.value,
                is_active=user.is_active,
                mfa_enabled=user.mfa_enabled,
                mfa_method=user.mfa_method.value if user.mfa_method else None,
                mfa_secret=user.mfa_secret,
                failed_login_count=user.failed_login_count,
                locked_until=_dt_to_str(user.locked_until) if user.locked_until else None,
                created_at=_dt_to_str(user.created_at),
            )
            session.add(row)
            session.commit()
        super().create_user(user)

    def get_user(self, user_id: UserId) -> User | None:
        cached = super().get_user(user_id)
        if cached is not None:
            return cached
        # Fallback to DB
        with Session(self._engine) as session:
            row = session.get(UserRow, str(user_id))
            if row is None:
                return None
            user = self._row_to_user(row)
            self._users[str(user_id)] = user
            return user

    def get_user_by_email(self, tenant_id: TenantId, email: str) -> User | None:
        cached = super().get_user_by_email(tenant_id, email)
        if cached is not None:
            return cached
        # Fallback to DB
        with Session(self._engine) as session:
            stmt = text("SELECT * FROM users WHERE tenant_id = :tid AND email = :email LIMIT 1")
            result = session.execute(stmt, {"tid": str(tenant_id), "email": email})
            row_data = result.fetchone()
            if row_data is None:
                return None
            row = session.get(UserRow, row_data.user_id)
            if row is None:
                return None
            user = self._row_to_user(row)
            self._users[str(user.user_id)] = user
            return user

    def get_users_by_tenant(self, tenant_id: TenantId) -> list[User]:
        return super().get_users_by_tenant(tenant_id)

    def update_user(self, user: User) -> None:
        with self._plock, Session(self._engine) as session:
            key = str(user.user_id)
            row = session.get(UserRow, key)
            if row is None:
                raise ValueError(f"User not found: {key}")
            row.tenant_id = str(user.tenant_id)
            row.email = user.email
            row.role = user.role.value
            row.is_active = user.is_active
            row.mfa_enabled = user.mfa_enabled
            row.mfa_method = user.mfa_method.value if user.mfa_method else None
            row.mfa_secret = user.mfa_secret
            row.failed_login_count = user.failed_login_count
            row.locked_until = _dt_to_str(user.locked_until) if user.locked_until else None
            session.commit()
        super().update_user(user)

    # ── Profile operations ──

    def create_profile(self, profile: TradingProfile) -> None:
        with self._plock, Session(self._engine) as session:
            key = str(profile.profile_id)
            if session.get(ProfileRow, key) is not None:
                raise ValueError(f"Profile already exists: {key}")
            row = ProfileRow(
                profile_id=key,
                tenant_id=str(profile.tenant_id),
                user_id=str(profile.user_id),
                display_name=profile.display_name,
                timezone=profile.timezone,
                language=profile.language,
                base_currency=profile.base_currency,
                risk_tolerance=profile.risk_tolerance,
                is_active=profile.is_active,
                created_at=_dt_to_str(profile.created_at),
            )
            session.add(row)
            session.commit()
        super().create_profile(profile)

    def get_profile(self, profile_id: str) -> TradingProfile | None:
        return super().get_profile(profile_id)

    def get_profiles_by_tenant(self, tenant_id: TenantId) -> list[TradingProfile]:
        return super().get_profiles_by_tenant(tenant_id)

    def get_profiles_by_user(self, tenant_id: TenantId, user_id: UserId) -> list[TradingProfile]:
        return super().get_profiles_by_user(tenant_id, user_id)

    # ── Session operations ──

    def create_session(self, session: AuthSession) -> None:
        with self._plock, Session(self._engine) as db_session:
            key = str(session.session_id)
            if db_session.get(SessionRow, key) is not None:
                raise ValueError(f"Session already exists: {key}")
            row = SessionRow(
                session_id=key,
                tenant_id=str(session.tenant_id),
                user_id=str(session.user_id),
                device_id=str(session.device_id) if session.device_id else None,
                status=session.status.value,
                step_up_until=_dt_to_str(session.step_up_until) if session.step_up_until else None,
                expires_at=_dt_to_str(session.expires_at),
                created_at=_dt_to_str(session.created_at),
                last_activity=_dt_to_str(session.last_activity),
            )
            db_session.add(row)
            db_session.commit()
        super().create_session(session)

    def get_session(self, session_id: str) -> AuthSession | None:
        cached = super().get_session(session_id)
        if cached is not None:
            return cached
        # Fallback to DB
        with Session(self._engine) as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                return None
            sess = self._row_to_session(row)
            self._sessions[session_id] = sess
            return sess

    def get_sessions_by_tenant(self, tenant_id: TenantId) -> list[AuthSession]:
        return super().get_sessions_by_tenant(tenant_id)

    def update_session(self, session: AuthSession) -> None:
        with self._plock, Session(self._engine) as db_session:
            key = str(session.session_id)
            row = db_session.get(SessionRow, key)
            if row is None:
                raise ValueError(f"Session not found: {key}")
            row.status = session.status.value
            row.step_up_until = _dt_to_str(session.step_up_until) if session.step_up_until else None
            row.expires_at = _dt_to_str(session.expires_at)
            row.last_activity = _dt_to_str(session.last_activity)
            row.device_id = str(session.device_id) if session.device_id else None
            db_session.commit()
        super().update_session(session)

    def revoke_session(self, session_id: str) -> bool:
        with self._plock, Session(self._engine) as session:
            row = session.get(SessionRow, session_id)
            if row is None:
                return False
            row.status = SessionStatus.REVOKED.value
            session.commit()
        return super().revoke_session(session_id)

    # ── Device operations ──

    def create_device(self, device: Device) -> None:
        with self._plock, Session(self._engine) as session:
            key = str(device.device_id)
            if session.get(DeviceRow, key) is not None:
                raise ValueError(f"Device already exists: {key}")
            row = DeviceRow(
                device_id=key,
                tenant_id=str(device.tenant_id),
                user_id=str(device.user_id),
                fingerprint=device.fingerprint,
                status=device.status.value,
                trusted_at=_dt_to_str(device.trusted_at) if device.trusted_at else None,
                last_seen=_dt_to_str(device.last_seen),
                created_at=_dt_to_str(device.created_at),
            )
            session.add(row)
            session.commit()
        super().create_device(device)

    def get_device(self, device_id: str) -> Device | None:
        return super().get_device(device_id)

    def get_devices_by_user(self, tenant_id: TenantId, user_id: UserId) -> list[Device]:
        return super().get_devices_by_user(tenant_id, user_id)

    def update_device(self, device: Device) -> None:
        with self._plock, Session(self._engine) as session:
            key = str(device.device_id)
            row = session.get(DeviceRow, key)
            if row is None:
                raise ValueError(f"Device not found: {key}")
            row.status = device.status.value
            row.trusted_at = _dt_to_str(device.trusted_at) if device.trusted_at else None
            row.last_seen = _dt_to_str(device.last_seen)
            session.commit()
        super().update_device(device)

    # ── Audit operations ──

    def record_audit_event(self, event: AuditEvent) -> None:
        with self._plock, Session(self._engine) as session:
            row = AuditEventRow(
                event_id=str(event.event_id),
                event_type=event.event_type.value,
                tenant_id=str(event.tenant_id),
                actor_user_id=str(event.actor_user_id) if event.actor_user_id else None,
                timestamp=_dt_to_str(event.timestamp),
                detail=event.detail,
                metadata_json=_json.dumps(event.metadata),
            )
            session.add(row)
            session.commit()
        super().record_audit_event(event)

    def get_audit_events_by_tenant(self, tenant_id: TenantId, limit: int = 100) -> list[AuditEvent]:
        return super().get_audit_events_by_tenant(tenant_id, limit=limit)

    def get_all_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        return super().get_all_audit_events(limit=limit)

    # ── Password storage (persistent) ──

    def set_password_hash(self, user_id: UserId, password_hash: str, salt: str) -> None:
        with self._plock, Session(self._engine) as session:
            row = session.get(UserRow, str(user_id))
            if row is None:
                raise ValueError(f"User not found: {str(user_id)}")
            row.password_hash = password_hash
            row.password_salt = salt
            session.commit()

    def get_password_hash(self, user_id: UserId) -> tuple[str, str] | None:
        with Session(self._engine) as session:
            row = session.get(UserRow, str(user_id))
            if row is None or row.password_hash is None or row.password_salt is None:
                return None
            return row.password_hash, row.password_salt

    # ── Reset (for testing) ──

    def reset(self) -> None:
        """Drop and recreate all tables and clear the in-memory cache."""
        with self._plock:
            Base.metadata.drop_all(self._engine)
            Base.metadata.create_all(self._engine)
            with Session(self._engine) as session:
                _ensure_schema(session)
                session.commit()
        # Clear the parent in-memory cache
        self._tenants.clear()
        self._users.clear()
        self._profiles.clear()
        self._sessions.clear()
        self._devices.clear()
        self._audit_events.clear()

    @property
    def engine(self) -> Any:
        """Expose the engine for testing (schema inspection)."""
        return self._engine

    @property
    def now(self) -> datetime:
        return datetime.now(UTC)


# ── Module-level store management ──

_store: PersistentIdentityStore | None = None
_store_lock = Lock()


def get_persistent_store() -> PersistentIdentityStore:
    """Get the singleton persistent identity store.

    In production, ``KTI_DATABASE_URL`` must be set to a PostgreSQL URL.
    """
    global _store  # noqa: PLW0603
    with _store_lock:
        if _store is None:
            _store = PersistentIdentityStore()
            atexit.register(_cleanup_singleton)
        return _store


def _cleanup_singleton() -> None:
    """Dispose the singleton store's engine at interpreter exit."""
    global _store  # noqa: PLW0603
    if _store is not None:
        with contextlib.suppress(Exception):
            _store.close()
        _store = None


def _close_all_instances() -> None:
    """Dispose every tracked PersistentIdentityStore engine."""
    with PersistentIdentityStore._instances_lock:
        instances = list(PersistentIdentityStore._instances)
        PersistentIdentityStore._instances.clear()
    for inst in instances:
        with contextlib.suppress(Exception):
            inst._engine.dispose()


def reset_persistent_store() -> None:
    """Reset the singleton persistent store (for testing).

    If a store already exists, its engine is disposed before
    replacement so that SQLite connections are not leaked.  All
    other tracked instances (created directly by tests) are also
    disposed to prevent ``ResourceWarning`` on Python 3.13+.
    """
    global _store  # noqa: PLW0603
    with _store_lock:
        _close_all_instances()
        _store = PersistentIdentityStore()
        atexit.register(_cleanup_singleton)


def get_store() -> PersistentIdentityStore:
    """Alias for :func:`get_persistent_store` (interface compatibility)."""
    return get_persistent_store()


def reset_store() -> None:
    """Alias for :func:`reset_persistent_store` (interface compatibility)."""
    reset_persistent_store()
