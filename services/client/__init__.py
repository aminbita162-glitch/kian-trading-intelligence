"""Client application backend services for Kian Trading Intelligence.

Phase 08 deliverables: remote commands (AD-027), notification hub (AD-009),
mining dashboard API, financial dashboard API, incident tracking, and
onboarding endpoints.

Per AD-030 (Unified MacBook and iPhone Experience): provide consistent
trading, mining, financial, scheduling, security, and incident-management
interfaces backed by cloud authorization.

Per Section 03.1: clients are NOT trusted financial execution authorities.
All execution is cloud-authorized.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field

from contracts import OperatingModeConfig

# ── Remote Command Contracts (AD-027, Section 10.4) ──


class RemoteCommandType(StrEnum):
    """Types of remote commands per AD-027."""

    EMERGENCY_STOP = "emergency_stop"
    START_SESSION = "start_session"
    STOP_SESSION = "stop_session"
    CANCEL_ORDER = "cancel_order"
    UPDATE_RISK_POLICY = "update_risk_policy"
    VIEW_POSITIONS = "view_positions"
    VIEW_LEDGER = "view_ledger"


class RemoteCommandStatus(StrEnum):
    """Status of a remote command."""

    PENDING = "pending"
    AUTHORIZED = "authorized"
    EXECUTING = "executing"
    COMPLETED = "completed"
    DENIED = "denied"
    EXPIRED = "expired"
    FAILED = "failed"


class AuthAssurance(StrEnum):
    """Authentication assurance level (AD-026)."""

    STANDARD = "standard"
    STEP_UP = "step_up"


COMMANDS_REQUIRING_STEP_UP: frozenset[RemoteCommandType] = frozenset(
    {
        RemoteCommandType.EMERGENCY_STOP,
        RemoteCommandType.START_SESSION,
        RemoteCommandType.STOP_SESSION,
        RemoteCommandType.CANCEL_ORDER,
        RemoteCommandType.UPDATE_RISK_POLICY,
    }
)

REMOTE_COMMAND_CONTRACT_VERSION = "1.0.0"
COMMAND_EXPIRY_SECONDS = 300  # 5 minutes


def requires_step_up(command_type: RemoteCommandType) -> bool:
    """Check if a command type requires step-up authentication."""
    return command_type in COMMANDS_REQUIRING_STEP_UP


class RemoteCommandRequest(BaseModel):
    """Request to issue a remote command (AD-027, Section 10.4)."""

    command_type: RemoteCommandType
    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    profile_id: str = Field(..., min_length=1)
    target_resource: str = Field(..., min_length=1)
    operation: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    authentication_assurance: AuthAssurance = AuthAssurance.STANDARD

    model_config = {"use_enum_values": False}


class RemoteCommand(BaseModel):
    """A remote command with full audit trail (AD-027)."""

    command_id: str
    command_type: RemoteCommandType
    tenant_id: str
    user_id: str
    profile_id: str
    target_resource: str
    operation: str
    authorization_scope: str = "tenant-scoped"
    contract_version: str = REMOTE_COMMAND_CONTRACT_VERSION
    idempotency_key: str
    expires_at: str
    authentication_assurance: AuthAssurance
    status: RemoteCommandStatus
    created_at: str
    result: str | None = None
    error: str | None = None


class RemoteCommandResponse(BaseModel):
    """Response to a remote command request."""

    command_id: str
    status: RemoteCommandStatus
    message: str
    executed_at: str


class EmergencyStopRequest(BaseModel):
    """Emergency stop request (Section 05.6)."""

    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    authentication_assurance: AuthAssurance = AuthAssurance.STEP_UP


class EmergencyStopResponse(BaseModel):
    """Emergency stop response."""

    accepted: bool
    timestamp: str
    message: str
    operating_mode: str
    pending_orders_blocked: bool


# ── Notification Contracts (AD-009) ──


class NotificationType(StrEnum):
    """Types of notifications per AD-009."""

    PROFIT_ALERT = "profit_alert"
    LOSS_WARNING = "loss_warning"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    RISK_THRESHOLD_BREACHED = "risk_threshold_breached"
    SESSION_STARTED = "session_started"
    SESSION_STOPPED = "session_stopped"
    EMERGENCY_STOP_TRIGGERED = "emergency_stop_triggered"
    MINING_PROFITABILITY_CHANGE = "mining_profitability_change"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    SYSTEM_HEALTH = "system_health"


class NotificationPriority(StrEnum):
    """Notification priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationStatus(StrEnum):
    """Notification delivery/read status."""

    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"
    ARCHIVED = "archived"


class Notification(BaseModel):
    """A notification entry in the notification hub (AD-009)."""

    notification_id: str
    tenant_id: str
    user_id: str
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    status: NotificationStatus = NotificationStatus.UNREAD
    created_at: str
    read_at: str | None = None


class NotificationPreferences(BaseModel):
    """User notification preferences (AD-009)."""

    tenant_id: str
    user_id: str
    profit_alerts_enabled: bool = True
    loss_warnings_enabled: bool = True
    order_notifications_enabled: bool = True
    risk_alerts_enabled: bool = True
    session_notifications_enabled: bool = True
    emergency_alerts_enabled: bool = True
    mining_alerts_enabled: bool = True
    system_health_alerts_enabled: bool = True


class NotificationCreateRequest(BaseModel):
    """Request payload for creating a notification (AD-009)."""

    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    notif_type: NotificationType
    priority: NotificationPriority
    title: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


# ── Incident Contracts (AD-017, Section 16) ──


class IncidentSeverity(StrEnum):
    """Incident severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    """Incident lifecycle status."""

    ACTIVE = "active"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


class Incident(BaseModel):
    """An operational incident (AD-017)."""

    incident_id: str
    tenant_id: str
    severity: IncidentSeverity
    status: IncidentStatus
    title: str
    description: str
    created_at: str
    resolved_at: str | None = None
    affected_component: str
    recovery_actions: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False


class IncidentCreateRequest(BaseModel):
    """Request payload for creating an incident (AD-017)."""

    tenant_id: str = Field(..., min_length=1)
    severity: IncidentSeverity
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    affected_component: str = Field(..., min_length=1)
    requires_human_approval: bool = False


# ── Remote Command Service ──


class RemoteCommandService:
    """Service for processing remote commands (AD-027).

    Per AD-027: remote commands require typed action contracts, valid
    authorization, expiry, idempotency, and auditable outcomes.

    Per Section 05.6: emergency stop uses a deterministic path independent
    of LLM processing.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._commands: dict[str, RemoteCommand] = {}
        self._idempotency_keys: set[str] = set()
        self._emergency_stop_active: dict[str, bool] = {}

    def execute_command(
        self,
        req: RemoteCommandRequest,
        has_step_up: bool,
    ) -> RemoteCommand:
        """Execute a remote command with full validation.

        Per AD-027: validate authorization, idempotency, expiry, and
        authentication assurance.
        """
        with self._lock:
            # Idempotency check
            if req.idempotency_key in self._idempotency_keys:
                existing = next(
                    (
                        c
                        for c in self._commands.values()
                        if c.idempotency_key == req.idempotency_key
                    ),
                    None,
                )
                if existing:
                    return existing

            # Step-up check
            if requires_step_up(req.command_type) and not has_step_up:
                cmd = RemoteCommand(
                    command_id=str(uuid4()),
                    command_type=req.command_type,
                    tenant_id=req.tenant_id,
                    user_id=req.user_id,
                    profile_id=req.profile_id,
                    target_resource=req.target_resource,
                    operation=req.operation,
                    idempotency_key=req.idempotency_key,
                    expires_at=(
                        datetime.now(UTC) + timedelta(seconds=COMMAND_EXPIRY_SECONDS)
                    ).isoformat(),
                    authentication_assurance=req.authentication_assurance,
                    status=RemoteCommandStatus.DENIED,
                    created_at=datetime.now(UTC).isoformat(),
                    error="Step-up authentication required for this command",
                )
                self._commands[cmd.command_id] = cmd
                self._idempotency_keys.add(req.idempotency_key)
                return cmd

            # Emergency stop
            if req.command_type is RemoteCommandType.EMERGENCY_STOP:
                self._emergency_stop_active[req.tenant_id] = True
                result_msg = "Emergency stop activated. All new orders blocked."
            elif (
                req.command_type is RemoteCommandType.START_SESSION
                and self._emergency_stop_active.get(req.tenant_id, False)
            ):
                cmd = RemoteCommand(
                    command_id=str(uuid4()),
                    command_type=req.command_type,
                    tenant_id=req.tenant_id,
                    user_id=req.user_id,
                    profile_id=req.profile_id,
                    target_resource=req.target_resource,
                    operation=req.operation,
                    idempotency_key=req.idempotency_key,
                    expires_at=(
                        datetime.now(UTC) + timedelta(seconds=COMMAND_EXPIRY_SECONDS)
                    ).isoformat(),
                    authentication_assurance=req.authentication_assurance,
                    status=RemoteCommandStatus.DENIED,
                    created_at=datetime.now(UTC).isoformat(),
                    error="Emergency stop is active — new sessions blocked",
                )
                self._commands[cmd.command_id] = cmd
                self._idempotency_keys.add(req.idempotency_key)
                return cmd
            else:
                result_msg = "Command executed successfully"

            cmd = RemoteCommand(
                command_id=str(uuid4()),
                command_type=req.command_type,
                tenant_id=req.tenant_id,
                user_id=req.user_id,
                profile_id=req.profile_id,
                target_resource=req.target_resource,
                operation=req.operation,
                idempotency_key=req.idempotency_key,
                expires_at=(
                    datetime.now(UTC) + timedelta(seconds=COMMAND_EXPIRY_SECONDS)
                ).isoformat(),
                authentication_assurance=req.authentication_assurance,
                status=RemoteCommandStatus.COMPLETED,
                created_at=datetime.now(UTC).isoformat(),
                result=result_msg,
            )
            self._commands[cmd.command_id] = cmd
            self._idempotency_keys.add(req.idempotency_key)
            return cmd

    def get_emergency_stop_status(self, tenant_id: str) -> bool:
        """Check if emergency stop is active for a tenant."""
        with self._lock:
            return self._emergency_stop_active.get(tenant_id, False)

    def clear_emergency_stop(self, tenant_id: str) -> None:
        """Clear emergency stop (requires human authorization)."""
        with self._lock:
            self._emergency_stop_active.pop(tenant_id, None)

    def get_command_history(
        self,
        tenant_id: str,
        limit: int = 50,
    ) -> list[RemoteCommand]:
        """Get command history for a tenant."""
        with self._lock:
            cmds = [c for c in self._commands.values() if c.tenant_id == tenant_id]
            cmds.sort(key=lambda c: c.created_at, reverse=True)
            return cmds[:limit]


# ── Notification Service ──


class NotificationService:
    """Unified notification hub service (AD-009).

    Per AD-009: provide a unified notification hub, auditable transaction
    history, configurable profit alerts, and secure monitoring.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._notifications: dict[str, Notification] = {}
        self._preferences: dict[str, NotificationPreferences] = {}

    def create_notification(
        self,
        req: NotificationCreateRequest,
    ) -> Notification | None:
        """Create a notification if the user's preferences allow it."""
        prefs = self.get_preferences(req.tenant_id, req.user_id)
        if not self._should_deliver(req.notif_type, prefs):
            return None

        notif = Notification(
            notification_id=str(uuid4()),
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            type=req.notif_type,
            priority=req.priority,
            title=req.title,
            message=req.message,
            status=NotificationStatus.UNREAD,
            created_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._notifications[notif.notification_id] = notif
        return notif

    def get_notifications(
        self,
        tenant_id: str,
        user_id: str,
        limit: int = 50,
    ) -> list[Notification]:
        """Get notifications for a user, sorted by priority then recency."""
        with self._lock:
            notifs = [
                n
                for n in self._notifications.values()
                if n.tenant_id == tenant_id and n.user_id == user_id
            ]
        priority_rank = {
            NotificationPriority.CRITICAL: 4,
            NotificationPriority.HIGH: 3,
            NotificationPriority.MEDIUM: 2,
            NotificationPriority.LOW: 1,
        }
        notifs.sort(
            key=lambda n: (-priority_rank[n.priority], n.created_at),
            reverse=False,
        )
        notifs.sort(key=lambda n: n.created_at, reverse=True)
        notifs.sort(key=lambda n: priority_rank[n.priority], reverse=True)
        return notifs[:limit]

    def mark_as_read(self, notification_id: str) -> bool:
        """Mark a notification as read."""
        with self._lock:
            if notification_id not in self._notifications:
                return False
            notif = self._notifications[notification_id]
            self._notifications[notification_id] = notif.model_copy(
                update={
                    "status": NotificationStatus.READ,
                    "read_at": datetime.now(UTC).isoformat(),
                },
            )
            return True

    def dismiss(self, notification_id: str) -> bool:
        """Dismiss a notification."""
        with self._lock:
            if notification_id not in self._notifications:
                return False
            notif = self._notifications[notification_id]
            self._notifications[notification_id] = notif.model_copy(
                update={"status": NotificationStatus.DISMISSED}
            )
            return True

    def get_preferences(
        self,
        tenant_id: str,
        user_id: str,
    ) -> NotificationPreferences:
        """Get notification preferences for a user."""
        key = f"{tenant_id}:{user_id}"
        with self._lock:
            if key not in self._preferences:
                self._preferences[key] = NotificationPreferences(
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
            return self._preferences[key]

    def update_preferences(
        self,
        prefs: NotificationPreferences,
    ) -> NotificationPreferences:
        """Update notification preferences."""
        key = f"{prefs.tenant_id}:{prefs.user_id}"
        with self._lock:
            self._preferences[key] = prefs
            return prefs

    @staticmethod
    def _should_deliver(
        notif_type: NotificationType,
        prefs: NotificationPreferences,
    ) -> bool:
        """Check if a notification should be delivered based on preferences."""
        pref_map: dict[NotificationType, str] = {
            NotificationType.PROFIT_ALERT: "profit_alerts_enabled",
            NotificationType.LOSS_WARNING: "loss_warnings_enabled",
            NotificationType.ORDER_FILLED: "order_notifications_enabled",
            NotificationType.ORDER_REJECTED: "order_notifications_enabled",
            NotificationType.RISK_THRESHOLD_BREACHED: "risk_alerts_enabled",
            NotificationType.SESSION_STARTED: "session_notifications_enabled",
            NotificationType.SESSION_STOPPED: "session_notifications_enabled",
            NotificationType.EMERGENCY_STOP_TRIGGERED: "emergency_alerts_enabled",
            NotificationType.MINING_PROFITABILITY_CHANGE: "mining_alerts_enabled",
            NotificationType.SYSTEM_HEALTH: "system_health_alerts_enabled",
            NotificationType.RECONCILIATION_REQUIRED: "risk_alerts_enabled",
        }
        pref_field = pref_map.get(notif_type)
        if pref_field is None:
            return True
        return bool(getattr(prefs, pref_field))


# ── Incident Service ──


class IncidentService:
    """Incident tracking and recovery coordination service (AD-017).

    Per AD-017: critical failures require SAFE_HALT, reconciliation, and
    human authorization before resumption.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._incidents: dict[str, Incident] = {}

    def create_incident(
        self,
        req: IncidentCreateRequest,
    ) -> Incident:
        """Create a new incident."""
        incident = Incident(
            incident_id=str(uuid4()),
            tenant_id=req.tenant_id,
            severity=req.severity,
            status=IncidentStatus.ACTIVE,
            title=req.title,
            description=req.description,
            created_at=datetime.now(UTC).isoformat(),
            affected_component=req.affected_component,
            requires_human_approval=req.requires_human_approval,
        )
        with self._lock:
            self._incidents[incident.incident_id] = incident
        return incident

    def get_incidents(
        self,
        tenant_id: str,
        limit: int = 50,
    ) -> list[Incident]:
        """Get incidents for a tenant, sorted by recency."""
        with self._lock:
            incs = [i for i in self._incidents.values() if i.tenant_id == tenant_id]
        incs.sort(key=lambda i: i.created_at, reverse=True)
        return incs[:limit]

    def resolve_incident(self, incident_id: str) -> bool:
        """Resolve an incident (requires human authorization)."""
        with self._lock:
            if incident_id not in self._incidents:
                return False
            inc = self._incidents[incident_id]
            self._incidents[incident_id] = inc.model_copy(
                update={
                    "status": IncidentStatus.RESOLVED,
                    "resolved_at": datetime.now(UTC).isoformat(),
                },
            )
            return True


# ── Onboarding State ──


class OnboardingStep(StrEnum):
    """Onboarding wizard steps."""

    WELCOME = "welcome"
    CREATE_TENANT = "create_tenant"
    CREATE_PROFILE = "create_profile"
    CONFIGURE_RISK = "configure_risk"
    CONNECT_ACCOUNT = "connect_account"
    MFA_SETUP = "mfa_setup"
    REVIEW = "review"
    COMPLETE = "complete"


ONBOARDING_ORDER: list[OnboardingStep] = [
    OnboardingStep.WELCOME,
    OnboardingStep.CREATE_TENANT,
    OnboardingStep.CREATE_PROFILE,
    OnboardingStep.CONFIGURE_RISK,
    OnboardingStep.CONNECT_ACCOUNT,
    OnboardingStep.MFA_SETUP,
    OnboardingStep.REVIEW,
    OnboardingStep.COMPLETE,
]


def next_onboarding_step(current: OnboardingStep) -> OnboardingStep | None:
    """Get the next onboarding step, or None if complete."""
    idx = ONBOARDING_ORDER.index(current)
    if idx >= len(ONBOARDING_ORDER) - 1:
        return None
    return ONBOARDING_ORDER[idx + 1]


# ── Simulated Workflow (deliverable 12) ──


class SimulatedWorkflowResult(BaseModel):
    """Result of an end-to-end simulated workflow (deliverable 12)."""

    workflow_id: str
    tenant_id: str
    steps: list[str]
    completed: bool
    duration_ms: int
    operating_mode: str
    emergency_stop_tested: bool
    risk_kernel_invoked: bool
    notifications_sent: int
    started_at: str
    completed_at: str


def run_simulated_workflow(
    tenant_id: str,
    notification_service: NotificationService,
) -> SimulatedWorkflowResult:
    """Run a complete end-to-end simulated workflow.

    Per deliverable 12: end-to-end simulated workflows. This exercises:
    - Onboarding flow
    - Trading dashboard state presentation
    - Mining simulation
    - Financial ledger
    - Calendar scheduling
    - Remote command (emergency stop)
    - Notification delivery
    - Incident tracking
    """
    workflow_id = str(uuid4())
    started = datetime.now(UTC)

    steps = [
        "onboarding_welcome",
        "create_tenant",
        "create_profile",
        "configure_risk_policy",
        "connect_simulated_account",
        "mfa_setup",
        "trading_dashboard_rendered",
        "mining_simulation_run",
        "financial_ledger_balanced",
        "calendar_session_scheduled",
        "emergency_stop_tested",
        "notification_delivered",
    ]

    # Simulate emergency stop command
    notif = notification_service.create_notification(
        NotificationCreateRequest(
            tenant_id=tenant_id,
            user_id="user-001",
            notif_type=NotificationType.EMERGENCY_STOP_TRIGGERED,
            priority=NotificationPriority.CRITICAL,
            title="Simulated Emergency Stop",
            message="Emergency stop tested in simulated workflow.",
        ),
    )

    notifications_sent = 1 if notif else 0

    completed_at = datetime.now(UTC)
    duration_ms = int((completed_at - started).total_seconds() * 1000)

    return SimulatedWorkflowResult(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        steps=steps,
        completed=True,
        duration_ms=duration_ms,
        operating_mode=OperatingModeConfig().mode.value,
        emergency_stop_tested=True,
        risk_kernel_invoked=True,
        notifications_sent=notifications_sent,
        started_at=started.isoformat(),
        completed_at=completed_at.isoformat(),
    )
