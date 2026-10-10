"""Security contracts tests for Phase 09 — Security, Resilience, and Scale.

Per Section 17 PHASE 09 deliverables:
1. Threat-model review (AD-010, AD-022)
2. Security scanning (AD-010)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from contracts.security import (
    BackupId,
    BackupRecord,
    BackupStatus,
    BackupType,
    CostEvaluation,
    CostEvaluationId,
    DisasterRecoveryState,
    FaultId,
    FaultInjectionResult,
    FaultInjectionStatus,
    FaultType,
    LoadTestId,
    LoadTestResult,
    MetricId,
    MetricType,
    NodeId,
    NodeState,
    ObservabilityMetric,
    ObservabilityReport,
    RecoveryId,
    RecoveryPhase,
    ScanId,
    ScanResult,
    ScanStatus,
    ScanType,
    SplitBrainDetection,
    SplitBrainRole,
    ThreatFinding,
    ThreatFindingId,
    ThreatModelReport,
    ThreatSeverity,
    ThreatStatus,
)

# ── Threat Model Contracts ──


class TestThreatFinding:
    """Test ThreatFinding contract (deliverable 1)."""

    def test_threat_finding_creation(self) -> None:
        finding = ThreatFinding(
            finding_id=ThreatFindingId.generate(),
            component="credential_vault",
            threat_vector="XOR encryption is reversible",
            severity=ThreatSeverity.HIGH,
            status=ThreatStatus.OPEN,
        )
        assert finding.severity is ThreatSeverity.HIGH
        assert finding.status is ThreatStatus.OPEN
        assert finding.component == "credential_vault"

    def test_threat_finding_resolve(self) -> None:
        finding = ThreatFinding(
            finding_id=ThreatFindingId.generate(),
            component="credential_vault",
            threat_vector="XOR encryption is reversible",
            severity=ThreatSeverity.HIGH,
            status=ThreatStatus.OPEN,
        )
        resolved = finding.resolve("Switched to KMS-backed encryption")
        assert resolved.status is ThreatStatus.RESOLVED
        assert resolved.resolved_at is not None
        assert resolved.mitigation == "Switched to KMS-backed encryption"

    def test_threat_finding_mitigate(self) -> None:
        finding = ThreatFinding(
            finding_id=ThreatFindingId.generate(),
            component="auth",
            threat_vector="No rate limiting on login",
            severity=ThreatSeverity.MEDIUM,
            status=ThreatStatus.OPEN,
        )
        mitigated = finding.mitigate("Added rate limiting")
        assert mitigated.status is ThreatStatus.MITIGATED
        assert mitigated.mitigation == "Added rate limiting"

    def test_threat_finding_empty_component_rejected(self) -> None:
        with pytest.raises(ValueError, match="component must not be empty"):
            ThreatFinding(
                finding_id=ThreatFindingId.generate(),
                component="",
                threat_vector="test",
                severity=ThreatSeverity.LOW,
            )

    def test_threat_finding_empty_vector_rejected(self) -> None:
        with pytest.raises(ValueError, match="threat_vector must not be empty"):
            ThreatFinding(
                finding_id=ThreatFindingId.generate(),
                component="test",
                threat_vector="",
                severity=ThreatSeverity.LOW,
            )

    def test_resolve_requires_resolved_at(self) -> None:
        with pytest.raises(ValueError, match="resolved_at must be set"):
            ThreatFinding(
                finding_id=ThreatFindingId.generate(),
                component="test",
                threat_vector="test",
                severity=ThreatSeverity.LOW,
                status=ThreatStatus.RESOLVED,
            )


class TestThreatModelReport:
    """Test ThreatModelReport contract (deliverable 1)."""

    def test_report_creation(self) -> None:
        report = ThreatModelReport(
            report_id=UUID("12345678-1234-1234-1234-123456789abc"),
            scope="Full platform zero-trust review",
        )
        assert report.scope == "Full platform zero-trust review"
        assert report.findings == []
        assert report.critical_findings == 0
        assert report.open_count == 0
        assert not report.has_blocking_findings

    def test_report_with_findings(self) -> None:
        report = ThreatModelReport(
            report_id=UUID("12345678-1234-1234-1234-123456789abc"),
            scope="Identity service review",
            findings=[
                ThreatFinding(
                    finding_id=ThreatFindingId.generate(),
                    component="auth",
                    threat_vector="Password stored in memory",
                    severity=ThreatSeverity.CRITICAL,
                    status=ThreatStatus.OPEN,
                ),
                ThreatFinding(
                    finding_id=ThreatFindingId.generate(),
                    component="credential_vault",
                    threat_vector="XOR encryption",
                    severity=ThreatSeverity.HIGH,
                    status=ThreatStatus.OPEN,
                ),
                ThreatFinding(
                    finding_id=ThreatFindingId.generate(),
                    component="logging",
                    threat_vector="Verbose error messages",
                    severity=ThreatSeverity.LOW,
                    status=ThreatStatus.RESOLVED,
                    resolved_at=datetime.now(UTC),
                ),
            ],
        )
        assert report.critical_findings == 1
        assert report.high_findings == 1
        assert report.open_count == 2
        assert report.resolved_count == 1
        assert report.has_blocking_findings

    def test_no_blocking_when_resolved(self) -> None:
        report = ThreatModelReport(
            report_id=UUID("12345678-1234-1234-1234-123456789abc"),
            scope="test",
            findings=[
                ThreatFinding(
                    finding_id=ThreatFindingId.generate(),
                    component="auth",
                    threat_vector="test",
                    severity=ThreatSeverity.CRITICAL,
                    status=ThreatStatus.RESOLVED,
                    resolved_at=datetime.now(UTC),
                ),
            ],
        )
        assert not report.has_blocking_findings


# ── Scan Result Contracts ──


class TestScanResult:
    """Test ScanResult contract (deliverable 2)."""

    def test_pass_scan(self) -> None:
        result = ScanResult.pass_scan(
            ScanType.SECRET_SCAN,
            "services/",
        )
        assert result.status is ScanStatus.PASSED
        assert result.findings_count == 0
        assert result.findings == []

    def test_fail_scan(self) -> None:
        result = ScanResult.fail_scan(
            ScanType.STATIC_ANALYSIS,
            "services/identity/",
            ["Unused variable in auth.py", "Missing type annotation"],
        )
        assert result.status is ScanStatus.FAILED
        assert result.findings_count == 2
        assert len(result.findings) == 2

    def test_pass_with_findings_rejected(self) -> None:
        with pytest.raises(ValueError, match="PASSED scan must have 0 findings"):
            ScanResult(
                scan_id=ScanId.generate(),
                scan_type=ScanType.SECRET_SCAN,
                component="test",
                status=ScanStatus.PASSED,
                findings_count=1,
                findings=["finding"],
            )

    def test_findings_count_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="findings_count must equal"):
            ScanResult(
                scan_id=ScanId.generate(),
                scan_type=ScanType.SECRET_SCAN,
                component="test",
                status=ScanStatus.FAILED,
                findings_count=5,
                findings=["one"],
            )


# ── Backup Contracts ──


class TestBackupRecord:
    """Test BackupRecord contract (deliverable 6)."""

    def test_backup_creation(self) -> None:
        backup = BackupRecord(
            backup_id=BackupId.generate(),
            tenant_id="tenant-1",
            backup_type=BackupType.FULL,
        )
        assert backup.status is BackupStatus.PENDING
        assert backup.completed_at is None

    def test_backup_complete(self) -> None:
        backup = BackupRecord(
            backup_id=BackupId.generate(),
            tenant_id="tenant-1",
            backup_type=BackupType.FULL,
        )
        completed = backup.complete("sha256:abc123", 1024)
        assert completed.status is BackupStatus.COMPLETED
        assert completed.completed_at is not None
        assert completed.data_checksum == "sha256:abc123"
        assert completed.size_bytes == 1024

    def test_backup_restore(self) -> None:
        backup = BackupRecord(
            backup_id=BackupId.generate(),
            tenant_id="tenant-1",
            backup_type=BackupType.SNAPSHOT,
        )
        completed = backup.complete("sha256:abc", 512)
        restored = completed.restore()
        assert restored.status is BackupStatus.RESTORED
        assert restored.restored_at is not None

    def test_restore_pending_rejected(self) -> None:
        backup = BackupRecord(
            backup_id=BackupId.generate(),
            tenant_id="tenant-1",
            backup_type=BackupType.FULL,
        )
        with pytest.raises(ValueError, match="Cannot restore backup in status"):
            backup.restore()

    def test_backup_types(self) -> None:
        for bt in BackupType:
            backup = BackupRecord(
                backup_id=BackupId.generate(),
                tenant_id="tenant-1",
                backup_type=bt,
            )
            assert backup.backup_type is bt


# ── Disaster Recovery Contracts ──


class TestDisasterRecoveryState:
    """Test DisasterRecoveryState contract (deliverable 7)."""

    def test_recovery_initial_state(self) -> None:
        state = DisasterRecoveryState(
            recovery_id=RecoveryId.generate(),
            tenant_id="tenant-1",
        )
        assert state.phase is RecoveryPhase.INFRASTRUCTURE_RECOVERY
        assert not state.is_complete
        assert not state.human_authorized

    def test_recovery_full_flow(self) -> None:
        state = DisasterRecoveryState(
            recovery_id=RecoveryId.generate(),
            tenant_id="tenant-1",
        )
        # Phase 1 -> 2
        state = state.advance_to_reconciliation()
        assert state.phase is RecoveryPhase.DATA_RECONCILIATION

        # Phase 2 -> 3
        state = state.complete_reconciliation()
        assert state.phase is RecoveryPhase.HUMAN_AUTHORIZATION
        assert state.reconciliation_completed

        # Phase 3 -> 4
        state = state.grant_human_authorization()
        assert state.phase is RecoveryPhase.TRADING_RESUMPTION
        assert state.human_authorized

        # Phase 4 -> complete
        state = state.complete()
        assert state.is_complete

    def test_skip_to_trading_rejected(self) -> None:
        state = DisasterRecoveryState(
            recovery_id=RecoveryId.generate(),
            tenant_id="tenant-1",
        )
        with pytest.raises(ValueError, match="Skipping human authorization"):
            state.skip_to_trading()

    def test_advance_from_wrong_phase_rejected(self) -> None:
        state = DisasterRecoveryState(
            recovery_id=RecoveryId.generate(),
            tenant_id="tenant-1",
            phase=RecoveryPhase.HUMAN_AUTHORIZATION,
            reconciliation_completed=True,
        )
        with pytest.raises(ValueError, match="Cannot advance to reconciliation"):
            state.advance_to_reconciliation()

    def test_authorize_without_reconciliation_rejected(self) -> None:
        state = DisasterRecoveryState(
            recovery_id=RecoveryId.generate(),
            tenant_id="tenant-1",
            phase=RecoveryPhase.HUMAN_AUTHORIZATION,
            reconciliation_completed=False,
        )
        with pytest.raises(ValueError, match="Cannot authorize trading"):
            state.grant_human_authorization()

    def test_complete_without_authorization_rejected(self) -> None:
        state = DisasterRecoveryState(
            recovery_id=RecoveryId.generate(),
            tenant_id="tenant-1",
            phase=RecoveryPhase.TRADING_RESUMPTION,
            human_authorized=False,
        )
        with pytest.raises(ValueError, match="without human authorization"):
            state.complete()

    def test_complete_from_wrong_phase_rejected(self) -> None:
        state = DisasterRecoveryState(
            recovery_id=RecoveryId.generate(),
            tenant_id="tenant-1",
            phase=RecoveryPhase.INFRASTRUCTURE_RECOVERY,
        )
        with pytest.raises(ValueError, match="Cannot complete from"):
            state.complete()


# ── Split-Brain Contracts ──


class TestNodeState:
    """Test NodeState contract (deliverable 8)."""

    def test_node_creation(self) -> None:
        node = NodeState(node_id=NodeId.generate())
        assert node.is_alive
        assert node.quorum_member

    def test_node_heartbeat(self) -> None:
        node = NodeState(node_id=NodeId.generate())
        old_heartbeat = node.last_heartbeat
        new_node = node.heartbeat()
        assert new_node.last_heartbeat > old_heartbeat

    def test_node_mark_dead(self) -> None:
        node = NodeState(node_id=NodeId.generate())
        dead = node.mark_dead()
        assert not dead.is_alive
        assert not dead.quorum_member

    def test_lease_expiry(self) -> None:
        node = NodeState(
            node_id=NodeId.generate(),
            lease_expires_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert node.lease_expired


class TestSplitBrainDetection:
    """Test SplitBrainDetection contract (deliverable 8)."""

    def test_no_split_brain(self) -> None:
        nodes = [
            NodeState(node_id=NodeId.generate(), role=SplitBrainRole.PRIMARY),
            NodeState(node_id=NodeId.generate(), role=SplitBrainRole.SECONDARY),
        ]
        detection = SplitBrainDetection(
            detection_id=UUID("12345678-1234-1234-1234-123456789abc"),
            nodes=nodes,
        )
        assert not detection.is_split_brain
        assert detection.primary_count == 1

    def test_split_brain_detected(self) -> None:
        nodes = [
            NodeState(node_id=NodeId.generate(), role=SplitBrainRole.PRIMARY),
            NodeState(node_id=NodeId.generate(), role=SplitBrainRole.PRIMARY),
        ]
        detection = SplitBrainDetection(
            detection_id=UUID("12345678-1234-1234-1234-123456789abc"),
            nodes=nodes,
            detected=True,
        )
        assert detection.is_split_brain
        assert detection.primary_count == 2


# ── Fault Injection Contracts ──


class TestFaultInjectionResult:
    """Test FaultInjectionResult contract (deliverable 9)."""

    def test_fault_creation(self) -> None:
        fault = FaultInjectionResult(
            fault_id=FaultId.generate(),
            fault_type=FaultType.NETWORK_TIMEOUT,
            target_component="exchange_adapter",
            status=FaultInjectionStatus.RECOVERED,
            detection_time_ms=5.0,
            recovery_time_ms=100.0,
            recovered_at=datetime.now(UTC),
        )
        assert fault.was_detected
        assert fault.was_recovered

    def test_undetected_fault(self) -> None:
        fault = FaultInjectionResult(
            fault_id=FaultId.generate(),
            fault_type=FaultType.DATABASE_FAILURE,
            target_component="ledger",
            status=FaultInjectionStatus.UNDETECTED,
        )
        assert not fault.was_detected
        assert not fault.was_recovered

    def test_recovered_without_recovered_at_rejected(self) -> None:
        with pytest.raises(ValueError, match="recovered_at must be set"):
            FaultInjectionResult(
                fault_id=FaultId.generate(),
                fault_type=FaultType.LATENCY_SPIKE,
                target_component="api",
                status=FaultInjectionStatus.RECOVERED,
            )

    def test_all_fault_types(self) -> None:
        for ft in FaultType:
            fault = FaultInjectionResult(
                fault_id=FaultId.generate(),
                fault_type=ft,
                target_component="test",
                status=FaultInjectionStatus.DETECTED,
            )
            assert fault.fault_type is ft


# ── Load Test Contracts ──


class TestLoadTestResult:
    """Test LoadTestResult contract (deliverable 10)."""

    def test_load_test_creation(self) -> None:
        result = LoadTestResult(
            test_id=LoadTestId.generate(),
            target_rps=100,
            actual_rps=98.5,
            total_requests=1000,
            successful_requests=950,
            failed_requests=50,
            p50_latency_ms=50.0,
            p95_latency_ms=120.0,
            p99_latency_ms=200.0,
            duration_seconds=10.0,
        )
        assert result.success_rate == 0.95
        assert result.meets_p95_target

    def test_load_test_request_count_validation(self) -> None:
        with pytest.raises(ValueError, match="successful_requests \\+ failed_requests"):
            LoadTestResult(
                test_id=LoadTestId.generate(),
                target_rps=100,
                actual_rps=100.0,
                total_requests=100,
                successful_requests=90,
                failed_requests=20,
                p50_latency_ms=50.0,
                p95_latency_ms=100.0,
                p99_latency_ms=200.0,
                duration_seconds=10.0,
            )

    def test_p95_write_target(self) -> None:
        result = LoadTestResult(
            test_id=LoadTestId.generate(),
            target_rps=100,
            actual_rps=100.0,
            total_requests=100,
            successful_requests=100,
            failed_requests=0,
            p50_latency_ms=100.0,
            p95_latency_ms=450.0,
            p99_latency_ms=600.0,
            duration_seconds=1.0,
        )
        assert result.meets_p95_target
        assert not result.meets_read_p95_target

    def test_p95_read_target(self) -> None:
        result = LoadTestResult(
            test_id=LoadTestId.generate(),
            target_rps=100,
            actual_rps=100.0,
            total_requests=100,
            successful_requests=100,
            failed_requests=0,
            p50_latency_ms=50.0,
            p95_latency_ms=250.0,
            p99_latency_ms=350.0,
            duration_seconds=1.0,
        )
        assert result.meets_p95_target
        assert result.meets_read_p95_target


# ── Observability Contracts ──


class TestObservabilityMetric:
    """Test ObservabilityMetric contract (deliverable 11)."""

    def test_metric_creation(self) -> None:
        metric = ObservabilityMetric(
            metric_id=MetricId.generate(),
            name="risk.assessments.total",
            metric_type=MetricType.COUNTER,
            value=12345.0,
            unit="count",
        )
        assert metric.name == "risk.assessments.total"
        assert metric.value == 12345.0

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name must not be empty"):
            ObservabilityMetric(
                metric_id=MetricId.generate(),
                name="",
                metric_type=MetricType.COUNTER,
                value=1.0,
            )

    def test_all_metric_types(self) -> None:
        for mt in MetricType:
            metric = ObservabilityMetric(
                metric_id=MetricId.generate(),
                name=f"test.{mt.value}",
                metric_type=mt,
                value=1.0,
            )
            assert metric.metric_type is mt


class TestObservabilityReport:
    """Test ObservabilityReport contract (deliverable 11)."""

    def test_all_verified(self) -> None:
        report = ObservabilityReport(
            report_id=UUID("12345678-1234-1234-1234-123456789abc"),
            metrics=[
                ObservabilityMetric(
                    metric_id=MetricId.generate(),
                    name="test",
                    metric_type=MetricType.COUNTER,
                    value=1.0,
                ),
            ],
            log_entries_verified=100,
            trace_entries_verified=50,
            audit_events_verified=25,
        )
        assert report.all_verified

    def test_not_all_verified(self) -> None:
        report = ObservabilityReport(
            report_id=UUID("12345678-1234-1234-1234-123456789abc"),
            metrics=[],
            log_entries_verified=0,
            trace_entries_verified=0,
            audit_events_verified=0,
        )
        assert not report.all_verified


# ── Cost Evaluation Contracts ──


class TestCostEvaluation:
    """Test CostEvaluation contract (deliverable 12)."""

    def test_cost_evaluation_creation(self) -> None:
        evaluation = CostEvaluation(
            evaluation_id=CostEvaluationId.generate(),
            tenant_id="tenant-1",
            llm_tokens_used=5000,
            llm_tokens_limit=10000,
            llm_cost_usd=0.50,
            infrastructure_cost_usd=10.00,
            deterministic_calls=100,
            llm_calls=20,
        )
        assert evaluation.token_utilization_pct == 50.0
        assert evaluation.within_budget
        assert evaluation.total_cost_usd == 10.50

    def test_cost_ratio(self) -> None:
        evaluation = CostEvaluation(
            evaluation_id=CostEvaluationId.generate(),
            tenant_id="tenant-1",
            llm_tokens_used=5000,
            llm_cost_usd=5.0,
            infrastructure_cost_usd=15.0,
        )
        assert evaluation.cost_ratio == 0.25

    def test_deterministic_ratio(self) -> None:
        evaluation = CostEvaluation(
            evaluation_id=CostEvaluationId.generate(),
            tenant_id="tenant-1",
            llm_tokens_used=100,
            deterministic_calls=80,
            llm_calls=20,
        )
        assert evaluation.deterministic_ratio == 0.8
        assert evaluation.meets_deterministic_first_target

    def test_over_budget(self) -> None:
        evaluation = CostEvaluation(
            evaluation_id=CostEvaluationId.generate(),
            tenant_id="tenant-1",
            llm_tokens_used=12000,
            llm_tokens_limit=10000,
        )
        assert not evaluation.within_budget
        assert evaluation.token_utilization_pct == 120.0

    def test_zero_cost_ratio(self) -> None:
        evaluation = CostEvaluation(
            evaluation_id=CostEvaluationId.generate(),
            tenant_id="tenant-1",
        )
        assert evaluation.cost_ratio == 0.0
        assert evaluation.total_cost_usd == 0.0

    def test_deterministic_first_not_met(self) -> None:
        evaluation = CostEvaluation(
            evaluation_id=CostEvaluationId.generate(),
            tenant_id="tenant-1",
            deterministic_calls=30,
            llm_calls=70,
        )
        assert not evaluation.meets_deterministic_first_target
        assert evaluation.deterministic_ratio == 30 / 100
