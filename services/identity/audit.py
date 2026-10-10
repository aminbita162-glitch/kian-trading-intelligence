"""Security audit event service for Kian Trading Intelligence.

Architecture Decisions: AD-022 (Observability and Audit).

Per Section 13: audit evidence must be tamper-evident and access-controlled.
Sensitive values must be redacted. Every security-relevant action must
produce an audit event.
"""

from __future__ import annotations

from contracts.identity import (
    AuditEvent,
    AuditEventType,
    TenantId,
    UserId,
)
from services.identity.database import get_store


def audit(
    *,
    event_type: AuditEventType,
    tenant_id: TenantId,
    actor_user_id: UserId | None = None,
    detail: str = "",
    metadata: dict[str, str] | None = None,
) -> AuditEvent:
    """Record a security audit event.

    Per AD-022: all security-relevant actions must be audited.
    Per Section 13: sensitive values in detail must be redacted by the caller.
    """
    event = AuditEvent.create(
        event_type=event_type,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        detail=detail,
        metadata=metadata,
    )
    get_store().record_audit_event(event)
    return event


def get_audit_events(
    tenant_id: TenantId,
    limit: int = 100,
) -> list[AuditEvent]:
    """Get audit events for a tenant.

    Per AD-010 and AD-022: audit events are tenant-scoped.
    Cross-tenant access is rejected.
    """
    return get_store().get_audit_events_by_tenant(tenant_id, limit=limit)


def get_all_audit_events(limit: int = 100) -> list[AuditEvent]:
    """Get all audit events (admin only)."""
    return get_store().get_all_audit_events(limit=limit)
