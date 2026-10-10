"""Tests for Phase 08 — Client Application contracts and services.

Per Section 17 Phase 08 deliverables:
1. Tauri MacBook application — tauri.conf.json, Cargo.toml, Rust source
2. Responsive iPhone PWA — manifest.json, responsive CSS, meta tags
3. Onboarding — OnboardingStep, next_onboarding_step, isOnboardingComplete
4. Trading dashboard — state presentation, risk exposure
5. Mining dashboard — simulation display, telemetry
6. Financial dashboard — ledger, P&L, thresholds, reservations
7. Calendar scheduler — session states, scheduling
8. Secure remote commands — AD-027 typed contracts, step-up, idempotency
9. Notification hub — AD-009 unified hub, preferences, priority
10. Connected-account settings — connection status, withdrawal prohibition
11. Incident and recovery interface — AD-017, severity, human approval
12. End-to-end simulated workflows — complete workflow exercise

Architecture decisions: AD-009, AD-027, AD-030, AD-031.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from services.client import (
    COMMANDS_REQUIRING_STEP_UP,
    REMOTE_COMMAND_CONTRACT_VERSION,
    AuthAssurance,
    IncidentCreateRequest,
    IncidentService,
    IncidentSeverity,
    IncidentStatus,
    NotificationCreateRequest,
    NotificationPriority,
    NotificationService,
    NotificationStatus,
    NotificationType,
    OnboardingStep,
    RemoteCommandRequest,
    RemoteCommandService,
    RemoteCommandStatus,
    RemoteCommandType,
    next_onboarding_step,
    requires_step_up,
    run_simulated_workflow,
)
from services.core.app import app

# ── Remote Command Tests (AD-027, deliverable 8) ──


class TestRemoteCommandTypes:
    """Test remote command type contracts."""

    def test_emergency_stop_requires_step_up(self) -> None:
        assert requires_step_up(RemoteCommandType.EMERGENCY_STOP)

    def test_start_session_requires_step_up(self) -> None:
        assert requires_step_up(RemoteCommandType.START_SESSION)

    def test_stop_session_requires_step_up(self) -> None:
        assert requires_step_up(RemoteCommandType.STOP_SESSION)

    def test_cancel_order_requires_step_up(self) -> None:
        assert requires_step_up(RemoteCommandType.CANCEL_ORDER)

    def test_update_risk_policy_requires_step_up(self) -> None:
        assert requires_step_up(RemoteCommandType.UPDATE_RISK_POLICY)

    def test_view_positions_does_not_require_step_up(self) -> None:
        assert not requires_step_up(RemoteCommandType.VIEW_POSITIONS)

    def test_view_ledger_does_not_require_step_up(self) -> None:
        assert not requires_step_up(RemoteCommandType.VIEW_LEDGER)

    def test_all_step_up_commands_are_five(self) -> None:
        assert len(COMMANDS_REQUIRING_STEP_UP) == 5

    def test_contract_version_is_1_0_0(self) -> None:
        assert REMOTE_COMMAND_CONTRACT_VERSION == "1.0.0"

    def test_all_command_types_present(self) -> None:
        types = list(RemoteCommandType)
        assert len(types) == 7


class TestRemoteCommandService:
    """Test the remote command service."""

    def _make_request(
        self,
        command_type: RemoteCommandType = RemoteCommandType.VIEW_POSITIONS,
        idempotency_key: str = "idem-001",
    ) -> RemoteCommandRequest:
        return RemoteCommandRequest(
            command_type=command_type,
            tenant_id="tenant-001",
            user_id="user-001",
            profile_id="profile-001",
            target_resource="positions",
            operation="view",
            idempotency_key=idempotency_key,
            authentication_assurance=AuthAssurance.STANDARD,
        )

    def test_view_positions_succeeds_without_step_up(self) -> None:
        svc = RemoteCommandService()
        cmd = svc.execute_command(self._make_request(), has_step_up=False)
        assert cmd.status is RemoteCommandStatus.COMPLETED

    def test_emergency_stop_denied_without_step_up(self) -> None:
        svc = RemoteCommandService()
        req = self._make_request(RemoteCommandType.EMERGENCY_STOP, "idem-es-001")
        cmd = svc.execute_command(req, has_step_up=False)
        assert cmd.status is RemoteCommandStatus.DENIED
        assert "Step-up authentication required" in (cmd.error or "")

    def test_emergency_stop_succeeds_with_step_up(self) -> None:
        svc = RemoteCommandService()
        req = self._make_request(RemoteCommandType.EMERGENCY_STOP, "idem-es-002")
        cmd = svc.execute_command(req, has_step_up=True)
        assert cmd.status is RemoteCommandStatus.COMPLETED

    def test_idempotency_returns_same_command(self) -> None:
        svc = RemoteCommandService()
        req = self._make_request(idempotency_key="idem-dup-001")
        cmd1 = svc.execute_command(req, has_step_up=False)
        cmd2 = svc.execute_command(req, has_step_up=False)
        assert cmd1.command_id == cmd2.command_id

    def test_different_idempotency_keys_different_commands(self) -> None:
        svc = RemoteCommandService()
        req1 = self._make_request(idempotency_key="idem-a")
        req2 = self._make_request(idempotency_key="idem-b")
        cmd1 = svc.execute_command(req1, has_step_up=False)
        cmd2 = svc.execute_command(req2, has_step_up=False)
        assert cmd1.command_id != cmd2.command_id

    def test_emergency_stop_blocks_start_session(self) -> None:
        svc = RemoteCommandService()
        # Issue emergency stop with step-up
        es_req = self._make_request(RemoteCommandType.EMERGENCY_STOP, "idem-block-001")
        svc.execute_command(es_req, has_step_up=True)
        # Try to start session — should be denied
        ss_req = self._make_request(RemoteCommandType.START_SESSION, "idem-block-002")
        cmd = svc.execute_command(ss_req, has_step_up=True)
        assert cmd.status is RemoteCommandStatus.DENIED
        assert "Emergency stop is active" in (cmd.error or "")

    def test_command_has_expiry(self) -> None:
        svc = RemoteCommandService()
        cmd = svc.execute_command(self._make_request(), has_step_up=False)
        assert cmd.expires_at is not None
        assert len(cmd.expires_at) > 0

    def test_command_has_contract_version(self) -> None:
        svc = RemoteCommandService()
        cmd = svc.execute_command(self._make_request(), has_step_up=False)
        assert cmd.contract_version == REMOTE_COMMAND_CONTRACT_VERSION

    def test_command_history_returns_tenant_commands(self) -> None:
        svc = RemoteCommandService()
        svc.execute_command(self._make_request(idempotency_key="h1"), has_step_up=False)
        svc.execute_command(self._make_request(idempotency_key="h2"), has_step_up=False)
        history = svc.get_command_history("tenant-001")
        assert len(history) == 2

    def test_command_history_isolated_by_tenant(self) -> None:
        svc = RemoteCommandService()
        req = RemoteCommandRequest(
            command_type=RemoteCommandType.VIEW_POSITIONS,
            tenant_id="tenant-other",
            user_id="user-001",
            profile_id="profile-001",
            target_resource="positions",
            operation="view",
            idempotency_key="idem-other",
            authentication_assurance=AuthAssurance.STANDARD,
        )
        svc.execute_command(req, has_step_up=False)
        history = svc.get_command_history("tenant-001")
        assert len(history) == 0


# ── Notification Tests (AD-009, deliverable 9) ──


class TestNotificationService:
    """Test the notification hub service."""

    def test_create_notification_returns_notification(self) -> None:
        svc = NotificationService()
        notif = svc.create_notification(
            NotificationCreateRequest(
                tenant_id="t1",
                user_id="u1",
                notif_type=NotificationType.PROFIT_ALERT,
                priority=NotificationPriority.MEDIUM,
                title="Test",
                message="Test message",
            ),
        )
        assert notif is not None
        assert notif.status is NotificationStatus.UNREAD

    def test_get_notifications_returns_user_notifications(self) -> None:
        svc = NotificationService()
        svc.create_notification(
            NotificationCreateRequest(
                tenant_id="t1",
                user_id="u1",
                notif_type=NotificationType.PROFIT_ALERT,
                priority=NotificationPriority.LOW,
                title="A",
                message="a",
            ),
        )
        svc.create_notification(
            NotificationCreateRequest(
                tenant_id="t1",
                user_id="u1",
                notif_type=NotificationType.LOSS_WARNING,
                priority=NotificationPriority.HIGH,
                title="B",
                message="b",
            ),
        )
        notifs = svc.get_notifications("t1", "u1")
        assert len(notifs) == 2

    def test_notifications_isolated_by_tenant(self) -> None:
        svc = NotificationService()
        svc.create_notification(
            NotificationCreateRequest(
                tenant_id="t1",
                user_id="u1",
                notif_type=NotificationType.PROFIT_ALERT,
                priority=NotificationPriority.LOW,
                title="A",
                message="a",
            ),
        )
        notifs = svc.get_notifications("t2", "u1")
        assert len(notifs) == 0

    def test_mark_as_read(self) -> None:
        svc = NotificationService()
        notif = svc.create_notification(
            NotificationCreateRequest(
                tenant_id="t1",
                user_id="u1",
                notif_type=NotificationType.PROFIT_ALERT,
                priority=NotificationPriority.LOW,
                title="A",
                message="a",
            ),
        )
        assert notif is not None
        assert svc.mark_as_read(notif.notification_id) is True
        notifs = svc.get_notifications("t1", "u1")
        assert notifs[0].status is NotificationStatus.READ
        assert notifs[0].read_at is not None

    def test_dismiss_notification(self) -> None:
        svc = NotificationService()
        notif = svc.create_notification(
            NotificationCreateRequest(
                tenant_id="t1",
                user_id="u1",
                notif_type=NotificationType.PROFIT_ALERT,
                priority=NotificationPriority.LOW,
                title="A",
                message="a",
            ),
        )
        assert notif is not None
        assert svc.dismiss(notif.notification_id) is True
        notifs = svc.get_notifications("t1", "u1")
        assert notifs[0].status is NotificationStatus.DISMISSED

    def test_preferences_default_all_enabled(self) -> None:
        svc = NotificationService()
        prefs = svc.get_preferences("t1", "u1")
        assert prefs.profit_alerts_enabled is True
        assert prefs.loss_warnings_enabled is True
        assert prefs.order_notifications_enabled is True
        assert prefs.risk_alerts_enabled is True
        assert prefs.emergency_alerts_enabled is True

    def test_disabled_preference_suppresses_notification(self) -> None:
        svc = NotificationService()
        prefs = svc.get_preferences("t1", "u1")
        prefs = prefs.model_copy(update={"profit_alerts_enabled": False})
        svc.update_preferences(prefs)
        notif = svc.create_notification(
            NotificationCreateRequest(
                tenant_id="t1",
                user_id="u1",
                notif_type=NotificationType.PROFIT_ALERT,
                priority=NotificationPriority.LOW,
                title="A",
                message="a",
            ),
        )
        assert notif is None

    def test_all_notification_types_present(self) -> None:
        types = list(NotificationType)
        assert len(types) == 11

    def test_all_priorities_present(self) -> None:
        priorities = list(NotificationPriority)
        assert len(priorities) == 4

    def test_all_statuses_present(self) -> None:
        statuses = list(NotificationStatus)
        assert len(statuses) == 4


# ── Incident Tests (AD-017, deliverable 11) ──


class TestIncidentService:
    """Test the incident tracking service."""

    def test_create_incident(self) -> None:
        svc = IncidentService()
        inc = svc.create_incident(
            IncidentCreateRequest(
                tenant_id="t1",
                severity=IncidentSeverity.WARNING,
                title="Test Incident",
                description="Test description",
                affected_component="trading-engine",
            ),
        )
        assert inc.status is IncidentStatus.ACTIVE
        assert inc.severity is IncidentSeverity.WARNING
        assert inc.requires_human_approval is False

    def test_get_incidents_by_tenant(self) -> None:
        svc = IncidentService()
        svc.create_incident(
            IncidentCreateRequest(
                tenant_id="t1",
                severity=IncidentSeverity.INFO,
                title="A",
                description="a",
                affected_component="comp-a",
            )
        )
        svc.create_incident(
            IncidentCreateRequest(
                tenant_id="t2",
                severity=IncidentSeverity.INFO,
                title="B",
                description="b",
                affected_component="comp-b",
            )
        )
        incs = svc.get_incidents("t1")
        assert len(incs) == 1
        assert incs[0].title == "A"

    def test_resolve_incident(self) -> None:
        svc = IncidentService()
        inc = svc.create_incident(
            IncidentCreateRequest(
                tenant_id="t1",
                severity=IncidentSeverity.CRITICAL,
                title="Critical",
                description="desc",
                affected_component="comp",
            ),
        )
        assert svc.resolve_incident(inc.incident_id) is True
        incs = svc.get_incidents("t1")
        assert incs[0].status is IncidentStatus.RESOLVED
        assert incs[0].resolved_at is not None

    def test_resolve_nonexistent_returns_false(self) -> None:
        svc = IncidentService()
        assert svc.resolve_incident("nonexistent") is False

    def test_all_severities_present(self) -> None:
        severities = list(IncidentSeverity)
        assert len(severities) == 3

    def test_all_incident_statuses_present(self) -> None:
        statuses = list(IncidentStatus)
        assert len(statuses) == 5

    def test_critical_incident_requires_human_approval(self) -> None:
        svc = IncidentService()
        inc = svc.create_incident(
            IncidentCreateRequest(
                tenant_id="t1",
                severity=IncidentSeverity.CRITICAL,
                title="Critical",
                description="desc",
                affected_component="comp",
                requires_human_approval=True,
            ),
        )
        assert inc.requires_human_approval is True


# ── Onboarding Tests (deliverable 3) ──


class TestOnboarding:
    """Test the onboarding flow."""

    def test_all_steps_present(self) -> None:
        steps = list(OnboardingStep)
        assert len(steps) == 8

    def test_welcome_is_first(self) -> None:
        assert list(OnboardingStep)[0] == OnboardingStep.WELCOME

    def test_complete_is_last(self) -> None:
        assert list(OnboardingStep)[-1] == OnboardingStep.COMPLETE

    def test_next_step_from_welcome(self) -> None:
        assert next_onboarding_step(OnboardingStep.WELCOME) == OnboardingStep.CREATE_TENANT

    def test_next_step_from_complete_is_none(self) -> None:
        assert next_onboarding_step(OnboardingStep.COMPLETE) is None

    def test_step_order_is_sequential(self) -> None:
        steps = list(OnboardingStep)
        expected = [
            "welcome",
            "create_tenant",
            "create_profile",
            "configure_risk",
            "connect_account",
            "mfa_setup",
            "review",
            "complete",
        ]
        assert [s.value for s in steps] == expected


# ── Simulated Workflow Tests (deliverable 12) ──


class TestSimulatedWorkflow:
    """Test the end-to-end simulated workflow."""

    def test_workflow_completes(self) -> None:
        notif_svc = NotificationService()
        result = run_simulated_workflow("t1", notif_svc)
        assert result.completed is True
        assert result.emergency_stop_tested is True
        assert result.risk_kernel_invoked is True
        assert result.operating_mode == "simulation"
        assert len(result.steps) > 0

    def test_workflow_has_workflow_id(self) -> None:
        notif_svc = NotificationService()
        result = run_simulated_workflow("t1", notif_svc)
        UUID(result.workflow_id)  # raises if not a UUID

    def test_workflow_sends_notification(self) -> None:
        notif_svc = NotificationService()
        result = run_simulated_workflow("t1", notif_svc)
        assert result.notifications_sent >= 1

    def test_workflow_exercises_all_dashboard_areas(self) -> None:
        notif_svc = NotificationService()
        result = run_simulated_workflow("t1", notif_svc)
        steps_str = " ".join(result.steps)
        assert "onboarding" in steps_str
        assert "trading" in steps_str
        assert "mining" in steps_str
        assert "financial" in steps_str
        assert "calendar" in steps_str
        assert "emergency_stop" in steps_str
        assert "notification" in steps_str


# ── API Endpoint Tests ──


class TestPhase08API:
    """Test Phase 08 API endpoints."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_health_endpoint(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["is_live"] is False
        assert data["operating_mode"] == "simulation"

    def test_remote_command_view_positions(self, client: TestClient) -> None:
        resp = client.post(
            "/remote-commands",
            json={
                "command_type": "view_positions",
                "tenant_id": "t1",
                "user_id": "u1",
                "profile_id": "p1",
                "target_resource": "positions",
                "operation": "view",
                "idempotency_key": "api-test-001",
                "authentication_assurance": "standard",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    def test_remote_command_emergency_stop_denied_without_step_up(self, client: TestClient) -> None:
        resp = client.post(
            "/remote-commands",
            json={
                "command_type": "emergency_stop",
                "tenant_id": "t1",
                "user_id": "u1",
                "profile_id": "p1",
                "target_resource": "all",
                "operation": "emergency_stop",
                "idempotency_key": "api-es-001",
                "authentication_assurance": "standard",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "denied"

    def test_remote_command_emergency_stop_with_step_up(self, client: TestClient) -> None:
        resp = client.post(
            "/remote-commands/emergency-stop",
            json={
                "tenant_id": "t1",
                "user_id": "u1",
                "reason": "Test emergency",
                "idempotency_key": "api-es-002",
                "authentication_assurance": "step_up",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["pending_orders_blocked"] is True

    def test_simulated_workflow_endpoint(self, client: TestClient) -> None:
        resp = client.post(
            "/workflows/simulated",
            params={"tenant_id": "t1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True
        assert data["operating_mode"] == "simulation"

    def test_onboarding_next_step(self, client: TestClient) -> None:
        resp = client.get(
            "/onboarding/next-step",
            params={"current": "welcome"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == "welcome"
        assert data["next"] == "create_tenant"

    def test_onboarding_next_step_complete(self, client: TestClient) -> None:
        resp = client.get(
            "/onboarding/next-step",
            params={"current": "complete"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["next"] is None

    def test_openapi_schema_contains_phase08_endpoints(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = schema.get("paths", {})
        assert "/remote-commands" in paths
        assert "/remote-commands/emergency-stop" in paths
        assert "/workflows/simulated" in paths
        assert "/onboarding/next-step" in paths
