"""Security service tests for Phase 09 — Security, Resilience, and Scale.

Per Section 17 PHASE 09 deliverables:
1. Threat-model review (AD-010, AD-022)
2. Security scanning (AD-010)
3. Tenant-isolation testing (AD-002, AD-010)
4. Risk stress tests (AD-013)
5. Financial stress tests (AD-018)
6. Backup restoration (AD-028)
7. Disaster recovery (AD-017, AD-028)
8. Split-brain simulation (AD-016, AD-028)
9. Fault injection (AD-023)
10. Load testing (AD-016)
11. Observability verification (AD-022)
12. Cost and token evaluation (AD-025)
"""

from __future__ import annotations

import pytest

from contracts.security import (
    BackupType,
    FaultType,
    MetricType,
    NodeId,
    NodeState,
    ScanType,
    SplitBrainRole,
    ThreatSeverity,
)
from services.security import (
    BackupService,
    CostEvaluator,
    DisasterRecoveryService,
    FaultInjector,
    FinancialStressTester,
    LoadTestRunner,
    ObservabilityVerifier,
    RiskStressTester,
    SecurityService,
    SplitBrainSimulator,
    TenantIsolationTester,
)

# ── Deliverable 1: Threat-Model Review ──


class TestSecurityServiceThreatModel:
    """Threat-model review service (deliverable 1)."""

    def test_create_threat_model_report(self) -> None:
        service = SecurityService()
        report = service.create_threat_model(
            scope="Full platform zero-trust review",
            components=["auth", "credential_vault", "ledger"],
        )
        assert report.scope == "Full platform zero-trust review"
        assert report.findings == []

    def test_add_and_resolve_finding(self) -> None:
        service = SecurityService()
        report = service.create_threat_model(
            scope="Identity service",
            components=["auth"],
        )
        finding = service.add_threat_finding(
            report,
            component="auth",
            threat_vector="Passwords stored in plaintext (memory)",
            severity=ThreatSeverity.CRITICAL,
        )
        assert finding.status.value == "open"
        assert report.critical_findings == 1
        assert report.has_blocking_findings

        resolved = service.resolve_finding(finding, "Migrated to hashed passwords")
        assert resolved.status.value == "resolved"
        assert resolved.resolved_at is not None

    def test_no_blocking_when_all_resolved(self) -> None:
        service = SecurityService()
        report = service.create_threat_model(
            scope="test",
            components=["test"],
        )
        f1 = service.add_threat_finding(
            report,
            component="c1",
            threat_vector="v1",
            severity=ThreatSeverity.HIGH,
        )
        # Replace the finding in the report with its resolved version
        resolved = service.resolve_finding(f1, "fixed")
        report.findings = [resolved]
        assert not report.has_blocking_findings


# ── Deliverable 2: Security Scanning ──


class TestSecurityServiceScanning:
    """Security scanning service (deliverable 2)."""

    def test_pass_scan(self) -> None:
        service = SecurityService()
        result = service.run_scan(ScanType.SECRET_SCAN, "services/")
        assert result.status.value == "passed"
        assert service.all_scans_passed()

    def test_fail_scan(self) -> None:
        service = SecurityService()
        result = service.run_scan(
            ScanType.STATIC_ANALYSIS,
            "services/identity/",
            ["Unused import in auth.py"],
        )
        assert result.status.value == "failed"
        assert not service.all_scans_passed()

    def test_all_scan_types(self) -> None:
        service = SecurityService()
        for scan_type in ScanType:
            result = service.run_scan(scan_type, "test")
            assert result.scan_type is scan_type

    def test_empty_scans_not_all_passed(self) -> None:
        service = SecurityService()
        assert not service.all_scans_passed()


# ── Deliverable 3: Tenant-Isolation Testing ──


class TestTenantIsolation:
    """Tenant-isolation testing service (deliverable 3).

    Per AD-002: tenant isolation from inception.
    Per Section 10.3: cross-tenant access rejected.
    """

    def test_cross_tenant_access_rejected(self) -> None:
        tester = TenantIsolationTester()
        result = tester.test_cross_tenant_access(
            source_tenant="tenant-a",
            target_tenant="tenant-b",
            resource="ledger_entry",
        )
        assert result is True
        assert tester.test_count == 1

    def test_same_tenant_rejected(self) -> None:
        tester = TenantIsolationTester()
        with pytest.raises(ValueError, match="must differ"):
            tester.test_cross_tenant_access(
                source_tenant="tenant-a",
                target_tenant="tenant-a",
                resource="test",
            )

    def test_data_isolation(self) -> None:
        tester = TenantIsolationTester()
        data_a = {"key_a": "value_a"}
        data_b = {"key_b": "value_b"}
        assert tester.test_tenant_data_isolation(data_a, data_b)

    def test_data_isolation_violation(self) -> None:
        tester = TenantIsolationTester()
        data_a = {"shared_key": "value_a"}
        data_b = {"shared_key": "value_b"}
        assert not tester.test_tenant_data_isolation(data_a, data_b)


# ── Deliverable 4: Risk Stress Tests ──


class TestRiskStress:
    """Risk stress testing service (deliverable 4).

    Per AD-013: hard limits for exposure, daily loss, drawdown,
    concentration.
    """

    def test_exposure_within_limit(self) -> None:
        tester = RiskStressTester()
        result = tester.stress_exposure_limit(
            max_exposure="100000.00",
            order_value="50000.00",
        )
        assert result["passed"] is True
        assert result["exceeded"] is False

    def test_exposure_exceeds_limit(self) -> None:
        tester = RiskStressTester()
        result = tester.stress_exposure_limit(
            max_exposure="100000.00",
            order_value="150000.00",
        )
        assert result["passed"] is False
        assert result["exceeded"] is True

    def test_daily_loss_within_limit(self) -> None:
        tester = RiskStressTester()
        result = tester.stress_daily_loss_limit(
            max_daily_loss="5000.00",
            current_loss="3000.00",
        )
        assert result["passed"] is True

    def test_daily_loss_exceeds_limit(self) -> None:
        tester = RiskStressTester()
        result = tester.stress_daily_loss_limit(
            max_daily_loss="5000.00",
            current_loss="6000.00",
        )
        assert result["passed"] is False
        assert result["exceeded"] is True

    def test_concentration_within_limit(self) -> None:
        tester = RiskStressTester()
        result = tester.stress_concentration_limit(
            max_concentration_pct="25.0",
            order_value="20000.00",
            max_position_value="100000.00",
        )
        assert result["passed"] is True

    def test_concentration_exceeds_limit(self) -> None:
        tester = RiskStressTester()
        result = tester.stress_concentration_limit(
            max_concentration_pct="25.0",
            order_value="50000.00",
            max_position_value="100000.00",
        )
        assert result["passed"] is False
        assert result["exceeded"] is True

    def test_emergency_stop_blocks_buys(self) -> None:
        tester = RiskStressTester()
        result = tester.stress_emergency_stop_blocks_orders(
            emergency_stop_active=True,
            order_side="buy",
        )
        assert result["blocked"] is True
        assert result["passed"] is True

    def test_emergency_stop_allows_sells(self) -> None:
        tester = RiskStressTester()
        result = tester.stress_emergency_stop_blocks_orders(
            emergency_stop_active=True,
            order_side="sell",
        )
        assert result["blocked"] is False


# ── Deliverable 5: Financial Stress Tests ──


class TestFinancialStress:
    """Financial stress testing service (deliverable 5).

    Per AD-018: balanced journal postings, exact decimal arithmetic.
    Per Section 07.1: ledger principles.
    """

    def test_balanced_double_entry(self) -> None:
        tester = FinancialStressTester()
        result = tester.stress_double_entry_balance(
            debits=["50000.00", "0.01"],
            credits=["50000.01"],
        )
        assert result["balanced"] is True

    def test_unbalanced_double_entry(self) -> None:
        tester = FinancialStressTester()
        result = tester.stress_double_entry_balance(
            debits=["50000.00"],
            credits=["50000.01"],
        )
        assert result["balanced"] is False
        assert result["passed"] is False

    def test_decimal_precision(self) -> None:
        tester = FinancialStressTester()
        result = tester.stress_decimal_precision(
            amount="0.12345678",
            precision=8,
        )
        assert result["correct"] is True

    def test_idempotent_posting_single(self) -> None:
        tester = FinancialStressTester()
        result = tester.stress_idempotent_posting(
            entry_id="entry-1",
            post_count=1,
        )
        assert result["idempotent"] is True

    def test_idempotent_posting_duplicate(self) -> None:
        tester = FinancialStressTester()
        result = tester.stress_idempotent_posting(
            entry_id="entry-1",
            post_count=2,
        )
        assert result["idempotent"] is False
        assert result["passed"] is False


# ── Deliverable 6: Backup Restoration ──


class TestBackupService:
    """Backup and restoration service (deliverable 6).

    Per AD-028: tested backups, point-in-time recovery.
    """

    def test_create_backup(self) -> None:
        service = BackupService()
        backup = service.create_backup("tenant-1", BackupType.FULL)
        assert backup.status.value == "completed"
        assert backup.data_checksum.startswith("sha256:")
        assert backup.size_bytes > 0
        assert service.backup_count == 1

    def test_restore_backup(self) -> None:
        service = BackupService()
        backup = service.create_backup("tenant-1")
        restored = service.restore_backup(str(backup.backup_id))
        assert restored.status.value == "restored"
        assert restored.restored_at is not None

    def test_verify_backup_integrity(self) -> None:
        service = BackupService()
        data = b"sensitive backup data"
        backup = service.create_backup("tenant-1", data=data)
        assert service.verify_backup(str(backup.backup_id), data)

    def test_verify_backup_wrong_data(self) -> None:
        service = BackupService()
        backup = service.create_backup("tenant-1", data=b"original")
        assert not service.verify_backup(str(backup.backup_id), b"tampered")

    def test_restore_nonexistent_rejected(self) -> None:
        service = BackupService()
        with pytest.raises(KeyError, match="not found"):
            service.restore_backup("nonexistent-id")

    def test_all_backup_types(self) -> None:
        service = BackupService()
        for bt in BackupType:
            backup = service.create_backup("tenant-1", bt)
            assert backup.backup_type is bt


# ── Deliverable 7: Disaster Recovery ──


class TestDisasterRecovery:
    """Disaster recovery service (deliverable 7).

    Per AD-017: SAFE_HALT, reconciliation, human authorization.
    Per Section 12: infrastructure recovery does NOT authorize
    trading recovery.
    """

    def test_start_recovery(self) -> None:
        service = DisasterRecoveryService()
        state = service.start_recovery("tenant-1")
        assert state.phase.value == "infrastructure_recovery"
        assert service.recovery_count == 1

    def test_full_recovery_flow(self) -> None:
        service = DisasterRecoveryService()
        state = service.start_recovery("tenant-1")
        assert state.phase.value == "infrastructure_recovery"

        state = service.advance_recovery(state)
        assert state.phase.value == "data_reconciliation"

        state = service.advance_recovery(state)
        assert state.phase.value == "human_authorization"

        state = service.advance_recovery(state)
        assert state.phase.value == "trading_resumption"

        state = service.advance_recovery(state)
        assert state.is_complete

    def test_recovery_requires_human_authorization(self) -> None:
        """Per Section 12: infrastructure recovery does NOT authorize
        trading recovery. Human authorization is mandatory."""
        service = DisasterRecoveryService()
        state = service.start_recovery("tenant-1")
        # Cannot skip human authorization
        with pytest.raises(ValueError, match="Skipping human authorization"):
            state.skip_to_trading()

    def test_recovery_from_wrong_phase_rejected(self) -> None:
        service = DisasterRecoveryService()
        state = service.start_recovery("tenant-1")
        # Already at infrastructure_recovery, can't complete
        with pytest.raises(ValueError, match="Cannot complete from"):
            state.complete()

    def test_get_recovery(self) -> None:
        service = DisasterRecoveryService()
        state = service.start_recovery("tenant-1")
        fetched = service.get_recovery(str(state.recovery_id))
        assert fetched.recovery_id == state.recovery_id


# ── Deliverable 8: Split-Brain Simulation ──


class TestSplitBrain:
    """Split-brain simulation service (deliverable 8).

    Per AD-028: split-brain protection.
    Per Section 12: split-brain protection.
    """

    def test_simulate_split_brain(self) -> None:
        simulator = SplitBrainSimulator()
        detection = simulator.simulate_split_brain(node_count=3)
        assert detection.detected
        assert len(detection.nodes) == 3
        assert len(detection.fenced_node_ids) == 2
        assert detection.active_node_id is not None

    def test_detect_split_brain(self) -> None:
        simulator = SplitBrainSimulator()
        nodes = [
            NodeState(
                node_id=NodeId.generate(),
                role=SplitBrainRole.PRIMARY,
                is_alive=True,
                quorum_member=True,
            ),
            NodeState(
                node_id=NodeId.generate(),
                role=SplitBrainRole.PRIMARY,
                is_alive=True,
                quorum_member=True,
            ),
        ]
        detection = simulator.detect_split_brain(nodes)
        assert detection.is_split_brain
        assert detection.detected
        assert len(detection.fenced_node_ids) == 1

    def test_detect_no_split_brain(self) -> None:
        simulator = SplitBrainSimulator()
        nodes = [
            NodeState(
                node_id=NodeId.generate(),
                role=SplitBrainRole.PRIMARY,
                is_alive=True,
                quorum_member=True,
            ),
            NodeState(
                node_id=NodeId.generate(),
                role=SplitBrainRole.SECONDARY,
                is_alive=True,
                quorum_member=True,
            ),
        ]
        detection = simulator.detect_split_brain(nodes)
        assert not detection.is_split_brain

    def test_resolve_split_brain(self) -> None:
        simulator = SplitBrainSimulator()
        detection = simulator.simulate_split_brain(node_count=3)
        resolved = simulator.resolve_split_brain(detection)
        assert not resolved.detected
        fenced_count = sum(1 for n in resolved.nodes if not n.is_alive)
        assert fenced_count == 2

    def test_split_brain_min_nodes(self) -> None:
        simulator = SplitBrainSimulator()
        with pytest.raises(ValueError, match="at least 2 nodes"):
            simulator.simulate_split_brain(node_count=1)


# ── Deliverable 9: Fault Injection ──


class TestFaultInjection:
    """Fault injection service (deliverable 9).

    Per AD-023: fault injection and repeatable verification.
    """

    def test_inject_fault_recovered(self) -> None:
        injector = FaultInjector()
        result = injector.inject_fault(
            FaultType.NETWORK_TIMEOUT,
            "exchange_adapter",
            detection_time_ms=5.0,
            recovery_time_ms=100.0,
        )
        assert result.was_detected
        assert result.was_recovered
        assert injector.all_detected
        assert injector.all_recovered

    def test_inject_undetected_fault(self) -> None:
        injector = FaultInjector()
        result = injector.inject_undetected_fault(
            FaultType.DATABASE_FAILURE,
            "ledger",
        )
        assert not result.was_detected
        assert not injector.all_detected

    def test_all_fault_types(self) -> None:
        injector = FaultInjector()
        for ft in FaultType:
            result = injector.inject_fault(ft, "test_component")
            assert result.fault_type is ft

    def test_fault_count(self) -> None:
        injector = FaultInjector()
        injector.inject_fault(FaultType.LATENCY_SPIKE, "api")
        injector.inject_fault(FaultType.PARTIAL_FAILURE, "queue")
        assert injector.fault_count == 2


# ── Deliverable 10: Load Testing ──


class TestLoadTest:
    """Load testing service (deliverable 10).

    Per AD-016: event-driven multi-tenant cloud.
    Per Section 14.1: design for 10,000 users.
    Per Section 14.2: provisional performance targets.
    """

    def test_synthetic_load_test(self) -> None:
        runner = LoadTestRunner()
        result = runner.run_synthetic_load_test(
            target_rps=100,
            total_requests=1000,
            p95_latency_ms=200.0,
            success_rate=1.0,
        )
        assert result.total_requests == 1000
        assert result.successful_requests == 1000
        assert result.failed_requests == 0
        assert result.meets_p95_target

    def test_load_test_with_failures(self) -> None:
        runner = LoadTestRunner()
        result = runner.run_synthetic_load_test(
            target_rps=500,
            total_requests=10000,
            p95_latency_ms=450.0,
            success_rate=0.95,
        )
        assert result.successful_requests == 9500
        assert result.failed_requests == 500
        assert result.success_rate == 0.95
        assert result.meets_p95_target

    def test_load_test_p95_exceeds_target(self) -> None:
        runner = LoadTestRunner()
        result = runner.run_synthetic_load_test(
            target_rps=100,
            total_requests=100,
            p95_latency_ms=600.0,
        )
        assert not result.meets_p95_target

    def test_load_test_read_target(self) -> None:
        runner = LoadTestRunner()
        result = runner.run_synthetic_load_test(
            target_rps=100,
            total_requests=100,
            p95_latency_ms=250.0,
        )
        assert result.meets_read_p95_target

    def test_load_test_invalid_rps(self) -> None:
        runner = LoadTestRunner()
        with pytest.raises(ValueError, match="target_rps must be positive"):
            runner.run_synthetic_load_test(
                target_rps=0,
                total_requests=100,
            )

    def test_load_test_invalid_success_rate(self) -> None:
        runner = LoadTestRunner()
        with pytest.raises(ValueError, match="success_rate"):
            runner.run_synthetic_load_test(
                target_rps=100,
                total_requests=100,
                success_rate=1.5,
            )

    def test_run_load_test_with_operations(self) -> None:
        """Run an actual load test with simple operations."""
        runner = LoadTestRunner()
        call_count = [0]

        def _simple_op() -> None:
            call_count[0] += 1

        result = runner.run_load_test(
            target_rps=100,
            duration_seconds=0.1,
            operations=[_simple_op],
        )
        assert result.total_requests > 0
        assert result.successful_requests > 0
        assert result.duration_seconds > 0


# ── Deliverable 11: Observability Verification ──


class TestObservability:
    """Observability verification service (deliverable 11).

    Per AD-022: structured logs, distributed traces, operational
    metrics, financial reconciliation metrics, risk decision records.
    """

    def test_create_metric(self) -> None:
        verifier = ObservabilityVerifier()
        metric = verifier.create_metric(
            name="risk.assessments.total",
            metric_type=MetricType.COUNTER,
            value=12345.0,
            unit="count",
        )
        assert metric.name == "risk.assessments.total"
        assert metric.value == 12345.0

    def test_verify_observability(self) -> None:
        verifier = ObservabilityVerifier()
        metric = verifier.create_metric(
            name="test.metric",
            metric_type=MetricType.GAUGE,
            value=42.0,
        )
        report = verifier.verify_observability(
            metrics=[metric],
            log_entries=100,
            trace_entries=50,
            audit_events=25,
        )
        assert report.all_verified
        assert report.log_entries_verified == 100
        assert report.trace_entries_verified == 50
        assert report.audit_events_verified == 25

    def test_verify_not_all_verified(self) -> None:
        verifier = ObservabilityVerifier()
        report = verifier.verify_observability(
            metrics=[],
            log_entries=0,
            trace_entries=0,
            audit_events=0,
        )
        assert not report.all_verified


# ── Deliverable 12: Cost and Token Evaluation ──


class TestCostEvaluation:
    """Cost and token evaluation service (deliverable 12).

    Per AD-025: bounded LLM usage, tenant quotas, rate limits.
    Per AD-003: deterministic-first processing.
    """

    def test_evaluate_costs(self) -> None:
        evaluator = CostEvaluator()
        evaluation = evaluator.evaluate_costs(
            tenant_id="tenant-1",
            llm_tokens_used=5000,
            llm_tokens_limit=10000,
            llm_cost_usd=0.50,
            infrastructure_cost_usd=10.0,
            deterministic_calls=100,
            llm_calls=20,
        )
        assert evaluation.within_budget
        assert evaluation.token_utilization_pct == 50.0
        assert evaluator.evaluation_count == 1

    def test_over_budget(self) -> None:
        evaluator = CostEvaluator()
        evaluation = evaluator.evaluate_costs(
            tenant_id="tenant-1",
            llm_tokens_used=15000,
            llm_tokens_limit=10000,
        )
        assert not evaluation.within_budget

    def test_deterministic_first(self) -> None:
        evaluator = CostEvaluator()
        evaluation = evaluator.evaluate_costs(
            tenant_id="tenant-1",
            llm_tokens_used=100,
            deterministic_calls=90,
            llm_calls=10,
        )
        assert evaluation.meets_deterministic_first_target

    def test_not_deterministic_first(self) -> None:
        evaluator = CostEvaluator()
        evaluation = evaluator.evaluate_costs(
            tenant_id="tenant-1",
            llm_tokens_used=100,
            deterministic_calls=20,
            llm_calls=80,
        )
        assert not evaluation.meets_deterministic_first_target

    def test_get_evaluation(self) -> None:
        evaluator = CostEvaluator()
        evaluation = evaluator.evaluate_costs("tenant-1", 100)
        fetched = evaluator.get_evaluation(str(evaluation.evaluation_id))
        assert fetched.evaluation_id == evaluation.evaluation_id
