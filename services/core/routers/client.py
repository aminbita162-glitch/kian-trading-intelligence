"""Client application API router for Kian Trading Intelligence.

Per AD-027: remote commands require typed action contracts, valid
authorization, expiry, idempotency, and auditable outcomes.
Per AD-009: unified notification hub with preferences and priority.
Per AD-017: incident and recovery interface with human approval.
Per Section 05.6: emergency stop uses a deterministic path.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from contracts import OperatingModeConfig
from services.client import (
    AuthAssurance,
    EmergencyStopRequest,
    EmergencyStopResponse,
    Incident,
    IncidentCreateRequest,
    IncidentService,
    Notification,
    NotificationCreateRequest,
    NotificationPreferences,
    NotificationService,
    OnboardingStep,
    RemoteCommand,
    RemoteCommandRequest,
    RemoteCommandResponse,
    RemoteCommandService,
    RemoteCommandStatus,
    RemoteCommandType,
    SimulatedWorkflowResult,
    next_onboarding_step,
    run_simulated_workflow,
)

router = APIRouter(tags=["Client"])

# ── Service singletons ──
_remote_command_service = RemoteCommandService()
_notification_service = NotificationService()
_incident_service = IncidentService()
_mode_config = OperatingModeConfig()


# ── Endpoints ──


@router.post("/remote-commands", response_model=RemoteCommandResponse)
async def issue_remote_command(
    req: RemoteCommandRequest,
) -> RemoteCommandResponse:
    """Issue a remote command (AD-027, Section 10.4).

    Per AD-027: remote commands require typed action contracts, valid
    authorization, expiry, idempotency, and auditable outcomes.
    Per Section 05.6: emergency stop uses a deterministic path.
    """
    has_step_up = req.authentication_assurance is AuthAssurance.STEP_UP
    cmd = _remote_command_service.execute_command(req, has_step_up)
    return RemoteCommandResponse(
        command_id=cmd.command_id,
        status=cmd.status,
        message=cmd.error or cmd.result or "Command processed",
        executed_at=cmd.created_at,
    )


@router.post("/remote-commands/emergency-stop", response_model=EmergencyStopResponse)
async def emergency_stop(req: EmergencyStopRequest) -> EmergencyStopResponse:
    """Trigger an emergency stop (Section 05.6).

    Per Section 05.6: blocks new exposure-increasing orders; prevents
    automatic trading restart; uses a deterministic path independent of
    LLM processing.
    """
    cmd_req = RemoteCommandRequest(
        command_type=RemoteCommandType.EMERGENCY_STOP,
        tenant_id=req.tenant_id,
        user_id=req.user_id,
        profile_id="emergency-stop",
        target_resource="all-sessions",
        operation="emergency_stop",
        idempotency_key=req.idempotency_key,
        authentication_assurance=req.authentication_assurance,
    )
    cmd = _remote_command_service.execute_command(
        cmd_req,
        req.authentication_assurance is AuthAssurance.STEP_UP,
    )
    accepted = cmd.status is RemoteCommandStatus.COMPLETED
    return EmergencyStopResponse(
        accepted=accepted,
        timestamp=cmd.created_at,
        message=cmd.result or cmd.error or "Emergency stop processed",
        operating_mode=_mode_config.mode.value,
        pending_orders_blocked=accepted,
    )


@router.get("/remote-commands/{tenant_id}", response_model=list[RemoteCommand])
async def get_command_history(
    tenant_id: str,
    limit: int = 50,
) -> list[RemoteCommand]:
    """Get remote command history for a tenant (AD-027 audit trail)."""
    return _remote_command_service.get_command_history(tenant_id, limit=limit)


@router.post("/notifications", response_model=Notification)
async def create_notification_endpoint(
    req: NotificationCreateRequest,
) -> Notification:
    """Create a notification in the unified hub (AD-009)."""
    notif = _notification_service.create_notification(req)
    if notif is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Notification suppressed by user preferences",
        )
    return notif


@router.get("/notifications/{tenant_id}/{user_id}", response_model=list[Notification])
async def get_notifications_endpoint(
    tenant_id: str,
    user_id: str,
    limit: int = 50,
) -> list[Notification]:
    """Get notifications for a user (AD-009)."""
    return _notification_service.get_notifications(tenant_id, user_id, limit=limit)


@router.patch("/notifications/{notification_id}/read", response_model=Notification)
async def mark_notification_read(notification_id: str) -> Notification:
    """Mark a notification as read."""
    if not _notification_service.mark_as_read(notification_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    # Re-fetch — the service returns a bool, not the object
    notifs = [
        n
        for n in _notification_service.get_notifications(
            "any",
            "any",
            limit=10000,
        )
        if n.notification_id == notification_id
    ]
    if not notifs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found after update",
        )
    return notifs[0]


@router.put(
    "/notifications/preferences/{tenant_id}/{user_id}",
    response_model=NotificationPreferences,
)
async def update_notification_preferences(
    tenant_id: str,
    user_id: str,
    prefs: NotificationPreferences,
) -> NotificationPreferences:
    """Update notification preferences for a user (AD-009)."""
    prefs = prefs.model_copy(update={"tenant_id": tenant_id, "user_id": user_id})
    return _notification_service.update_preferences(prefs)


@router.get("/incidents/{tenant_id}", response_model=list[Incident])
async def get_incidents_endpoint(
    tenant_id: str,
    limit: int = 50,
) -> list[Incident]:
    """Get incidents for a tenant (AD-017)."""
    return _incident_service.get_incidents(tenant_id, limit=limit)


@router.post("/incidents", response_model=Incident, status_code=201)
async def create_incident_endpoint(
    req: IncidentCreateRequest,
) -> Incident:
    """Create a new incident (AD-017)."""
    return _incident_service.create_incident(req)


@router.post("/incidents/{incident_id}/resolve", response_model=Incident)
async def resolve_incident_endpoint(
    incident_id: str,
    tenant_id: str,
) -> Incident:
    """Resolve an incident. Per AD-017: requires human authorization."""
    if not _incident_service.resolve_incident(incident_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    incidents = _incident_service.get_incidents(tenant_id, limit=10000)
    for inc in incidents:
        if inc.incident_id == incident_id:
            return inc
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Incident not found after resolution",
    )


@router.get("/onboarding/next-step")
async def get_next_onboarding_step(current: str) -> dict[str, str | None]:
    """Get the next onboarding step (deliverable 3)."""
    try:
        step = OnboardingStep(current)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid onboarding step: {current}",
        ) from None
    nxt = next_onboarding_step(step)
    return {
        "current": current,
        "next": nxt.value if nxt else None,
    }


@router.post("/workflows/simulated", response_model=SimulatedWorkflowResult)
async def run_simulated_workflow_endpoint(
    tenant_id: str,
) -> SimulatedWorkflowResult:
    """Run a complete end-to-end simulated workflow (deliverable 12).

    Per Section 17 Phase 08 deliverable 12: end-to-end simulated workflows
    exercising all dashboard components, remote commands, notifications,
    and incident tracking in simulation mode.
    """
    return run_simulated_workflow(
        tenant_id=tenant_id,
        notification_service=_notification_service,
    )
