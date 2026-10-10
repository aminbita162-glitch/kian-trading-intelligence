"""Session and device control service for Kian Trading Intelligence.

Architecture Decisions: AD-010 (Zero-Trust), AD-026 (Step-Up Authorization).

Sessions are revocable, tenant-scoped, and may require step-up
authentication for sensitive operations (AD-026).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from contracts.identity import AuthSession, SessionStatus, TenantId, UserId
from services.identity.database import get_store

DEFAULT_SESSION_DURATION = timedelta(hours=1)
DEFAULT_STEP_UP_DURATION = timedelta(minutes=15)


def create_session(
    *,
    tenant_id: TenantId,
    user_id: UserId,
    device_id: UUID | None = None,
    session_duration: timedelta | None = None,
) -> AuthSession:
    """Create a new authentication session."""
    store = get_store()
    session = AuthSession.create(
        tenant_id=tenant_id,
        user_id=user_id,
        device_id=device_id,
        session_duration=session_duration or DEFAULT_SESSION_DURATION,
    )
    store.create_session(session)
    return session


def get_session(session_id: str) -> AuthSession | None:
    """Retrieve a session by ID."""
    return get_store().get_session(session_id)


def validate_session(session_id: str) -> AuthSession:
    """Validate a session and return it if active.

    Raises:
        ValueError: If session is not found, expired, or revoked.
    """
    session = get_store().get_session(session_id)
    if session is None:
        raise ValueError("Session not found")
    if session.status == SessionStatus.REVOKED:
        raise ValueError("Session has been revoked")
    if session.is_expired:
        session.status = SessionStatus.EXPIRED
        get_store().update_session(session)
        raise ValueError("Session has expired")
    session.touch()
    get_store().update_session(session)
    return session


def revoke_session(session_id: str) -> bool:
    """Revoke a session by ID."""
    return get_store().revoke_session(session_id)


def require_step_up(session: AuthSession) -> None:
    """Mark a session as requiring step-up authentication."""
    session.require_step_up()
    get_store().update_session(session)


def grant_step_up(
    session: AuthSession,
    duration: timedelta | None = None,
) -> None:
    """Grant step-up authorization to a session."""
    session.grant_step_up(duration or DEFAULT_STEP_UP_DURATION)
    get_store().update_session(session)


def check_step_up(session: AuthSession) -> bool:
    """Check if a session has valid step-up authorization."""
    return session.has_step_up


def get_sessions_by_tenant(tenant_id: TenantId) -> list[AuthSession]:
    """Get all sessions for a tenant."""
    return get_store().get_sessions_by_tenant(tenant_id)
