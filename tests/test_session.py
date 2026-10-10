"""Adversarial session and device control tests for Phase 02.

Architecture Decisions: AD-010 (Zero-Trust), AD-026 (Step-Up Authorization).

Tests: session creation, validation, revocation, expiry, step-up lifecycle,
and device handling.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from contracts.identity import (
    AuthSession,
    SessionStatus,
    TenantId,
    UserId,
)
from services.identity.database import get_store
from services.identity.session import (
    create_session,
    get_session,
    grant_step_up,
    require_step_up,
    revoke_session,
    validate_session,
)
from services.identity.tenant import create_tenant


class TestSession:
    def _create_tenant_and_ids(self) -> tuple[TenantId, UserId]:
        """Create a tenant and return (tenant_id, user_id)."""
        tenant = create_tenant(name="Session Test Tenant")
        return tenant.tenant_id, UserId.generate()

    def test_create_session(self) -> None:
        """Session creation produces a valid session."""
        tenant_id, user_id = self._create_tenant_and_ids()
        session = create_session(tenant_id=tenant_id, user_id=user_id)
        assert session.user_id == user_id
        assert session.tenant_id == tenant_id
        assert session.status == SessionStatus.ACTIVE
        assert not session.is_expired

    def test_get_session(self) -> None:
        """get_session retrieves an existing session."""
        tenant_id, user_id = self._create_tenant_and_ids()
        session = create_session(tenant_id=tenant_id, user_id=user_id)
        retrieved = get_session(str(session.session_id))
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_get_nonexistent_session(self) -> None:
        """get_session returns None for non-existent session."""
        assert get_session(str(uuid4())) is None

    def test_validate_session(self) -> None:
        """validate_session returns an active session."""
        tenant_id, user_id = self._create_tenant_and_ids()
        session = create_session(tenant_id=tenant_id, user_id=user_id)
        validated = validate_session(str(session.session_id))
        assert validated.session_id == session.session_id

    def test_validate_nonexistent_session(self) -> None:
        """validate_session raises for non-existent session."""
        with pytest.raises(ValueError, match="not found"):
            validate_session(str(uuid4()))

    def test_revoke_session(self) -> None:
        """revoking a session sets status to REVOKED."""
        tenant_id, user_id = self._create_tenant_and_ids()
        session = create_session(tenant_id=tenant_id, user_id=user_id)
        assert revoke_session(str(session.session_id)) is True
        revoked = get_session(str(session.session_id))
        assert revoked is not None
        assert revoked.status == SessionStatus.REVOKED

    def test_revoke_nonexistent_session(self) -> None:
        """revoking a non-existent session returns False."""
        assert revoke_session(str(uuid4())) is False

    def test_validate_revoked_session(self) -> None:
        """validate_session rejects revoked sessions."""
        tenant_id, user_id = self._create_tenant_and_ids()
        session = create_session(tenant_id=tenant_id, user_id=user_id)
        revoke_session(str(session.session_id))
        with pytest.raises(ValueError, match="revoked"):
            validate_session(str(session.session_id))

    def test_expired_session(self) -> None:
        """An expired session is detected."""
        tenant_id, user_id = self._create_tenant_and_ids()
        # Create session that already expired
        session = AuthSession(
            session_id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            device_id=None,
            status=SessionStatus.ACTIVE,
            step_up_until=None,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        get_store().create_session(session)
        with pytest.raises(ValueError, match="expired"):
            validate_session(str(session.session_id))

    def test_step_up_lifecycle(self) -> None:
        """require_step_up then grant_step_up works correctly."""
        tenant_id, user_id = self._create_tenant_and_ids()
        session = create_session(tenant_id=tenant_id, user_id=user_id)
        # Initially no step-up
        assert not session.has_step_up
        # Require step-up
        require_step_up(session)
        assert session.status.value == "step_up_required"
        # Grant step-up
        grant_step_up(session)
        assert session.status.value == "active"
        assert session.has_step_up

    def test_session_with_device(self) -> None:
        """Session can be created with a device ID."""
        tenant_id, user_id = self._create_tenant_and_ids()
        device_id = uuid4()
        session = create_session(
            tenant_id=tenant_id,
            user_id=user_id,
            device_id=device_id,
        )
        assert session.device_id == device_id

    def test_session_custom_duration(self) -> None:
        """Session can have a custom duration."""
        tenant_id, user_id = self._create_tenant_and_ids()
        session = create_session(
            tenant_id=tenant_id,
            user_id=user_id,
            session_duration=timedelta(hours=2),
        )
        # Should not be expired
        assert not session.is_expired
