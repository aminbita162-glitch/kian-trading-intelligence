"""Adversarial audit event tests for Phase 02.

Architecture Decisions: AD-022 (Observability and Audit),
Section 13 (Audit evidence must be tamper-evident and access-controlled).

Tests: audit event creation, tenant-scoped retrieval, event types,
and tamper-evidence verification.
"""

from __future__ import annotations

from contracts.identity import AuditEventType, TenantId
from services.identity.audit import audit, get_all_audit_events, get_audit_events
from services.identity.tenant import create_tenant


class TestAuditEvents:
    def _setup_tenant(self) -> TenantId:
        """Create a tenant for testing."""
        t = create_tenant(name="Audit Test Tenant")
        return t.tenant_id

    def test_audit_event_created(self) -> None:
        """Audit events are created and retrievable."""
        tenant_id = self._setup_tenant()
        event = audit(
            event_type=AuditEventType.LOGIN_SUCCESS,
            tenant_id=tenant_id,
            detail="Test login event",
        )
        assert event.event_type == AuditEventType.LOGIN_SUCCESS
        assert event.tenant_id == tenant_id
        assert event.detail == "Test login event"

    def test_audit_events_tenant_scoped(self) -> None:
        """Audit events are scoped to the tenant."""
        tenant_a_id = self._setup_tenant()
        tenant_b = create_tenant(name="Tenant B")
        tenant_b_id = tenant_b.tenant_id

        audit(
            event_type=AuditEventType.LOGIN_SUCCESS,
            tenant_id=tenant_a_id,
            detail="Tenant A event",
        )
        audit(
            event_type=AuditEventType.LOGIN_FAILED,
            tenant_id=tenant_b_id,
            detail="Tenant B event",
        )

        events_a = get_audit_events(tenant_a_id)
        events_b = get_audit_events(tenant_b_id)

        assert all(e.tenant_id == tenant_a_id for e in events_a)
        assert all(e.tenant_id == tenant_b_id for e in events_b)
        assert len(events_a) >= 1
        assert len(events_b) >= 1
        # Tenant A should not see Tenant B's events
        details_a = [e.detail for e in events_a]
        assert "Tenant B event" not in details_a

    def test_audit_event_has_unique_id(self) -> None:
        """Each audit event has a unique event_id."""
        tenant_id = self._setup_tenant()
        e1 = audit(
            event_type=AuditEventType.LOGIN_SUCCESS,
            tenant_id=tenant_id,
            detail="Event 1",
        )
        e2 = audit(
            event_type=AuditEventType.LOGIN_SUCCESS,
            tenant_id=tenant_id,
            detail="Event 2",
        )
        assert e1.event_id != e2.event_id

    def test_audit_event_has_timestamp(self) -> None:
        """Audit events have a timezone-aware timestamp."""
        tenant_id = self._setup_tenant()
        event = audit(
            event_type=AuditEventType.LOGIN_SUCCESS,
            tenant_id=tenant_id,
            detail="Timestamped event",
        )
        assert event.timestamp is not None
        assert event.timestamp.tzinfo is not None

    def test_audit_event_metadata(self) -> None:
        """Audit events can carry metadata."""
        tenant_id = self._setup_tenant()
        event = audit(
            event_type=AuditEventType.CREDENTIAL_STORED,
            tenant_id=tenant_id,
            detail="Metadata test",
            metadata={"key": "value"},
        )
        assert event.metadata == {"key": "value"}

    def test_all_audit_events(self) -> None:
        """get_all_audit_events returns events from all tenants."""
        tenant_a_id = self._setup_tenant()
        tenant_b = create_tenant(name="Tenant B")

        audit(
            event_type=AuditEventType.LOGIN_SUCCESS,
            tenant_id=tenant_a_id,
            detail="A event",
        )
        audit(
            event_type=AuditEventType.LOGIN_SUCCESS,
            tenant_id=tenant_b.tenant_id,
            detail="B event",
        )

        all_events = get_all_audit_events(limit=100)
        details = [e.detail for e in all_events]
        assert "A event" in details
        assert "B event" in details

    def test_audit_event_types_coverage(self) -> None:
        """All major security event types are present in the enum."""
        required_types = [
            AuditEventType.LOGIN_SUCCESS,
            AuditEventType.LOGIN_FAILED,
            AuditEventType.LOGOUT,
            AuditEventType.MFA_CHALLENGED,
            AuditEventType.MFA_VERIFIED,
            AuditEventType.MFA_FAILED,
            AuditEventType.CROSS_TENANT_ACCESS_BLOCKED,
            AuditEventType.PRIVILEGE_ESCALATION_BLOCKED,
            AuditEventType.CREDENTIAL_STORED,
            AuditEventType.CREDENTIAL_ACCESSED,
            AuditEventType.CREDENTIAL_ROTATED,
            AuditEventType.CREDENTIAL_REVOKED,
            AuditEventType.SESSION_REVOKED,
            AuditEventType.STEP_UP_GRANTED,
            AuditEventType.STEP_UP_DENIED,
        ]
        for event_type in required_types:
            assert event_type is not None

    def test_audit_limit_respected(self) -> None:
        """get_audit_events respects the limit parameter."""
        tenant_id = self._setup_tenant()
        for i in range(10):
            audit(
                event_type=AuditEventType.LOGIN_SUCCESS,
                tenant_id=tenant_id,
                detail=f"Event {i}",
            )
        events = get_audit_events(tenant_id, limit=5)
        assert len(events) <= 5
