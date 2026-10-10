"""Release engineering contracts tests for Phase 10 — Release Engineering
and Controlled Launch.

Per Section 17 PHASE 10 deliverables:
1. Final architecture review (AD-033)
2. Dependency verification (AD-024)
3. Release artifact integrity (AD-024)
4. Migration verification (AD-024)
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from contracts.release import (
    ArtifactId,
    ArtifactType,
    CanaryDeployment,
    CanaryId,
    CanaryMetrics,
    CanaryStatus,
    DependencyId,
    DependencyRecord,
    DependencyStatus,
    DeploymentId,
    DeploymentStatus,
    DocId,
    DocStatus,
    DocType,
    DocumentationRecord,
    EvidenceId,
    EvidenceRecord,
    EvidenceType,
    FinalReadinessReport,
    GateResult,
    HealthCheckResult,
    IntegrityStatus,
    MigrationId,
    MigrationRecord,
    MigrationStatus,
    OperationalRunbook,
    ReadinessDecision,
    ReadinessReportId,
    ReleaseArtifact,
    ReleaseEvidencePackage,
    ReviewCategory,
    ReviewItem,
    ReviewItemId,
    ReviewStatus,
    RollbackId,
    RollbackStatus,
    RollbackTest,
    RunbookCategory,
    RunbookId,
    RunbookStep,
    StagingDeployment,
)


class TestReviewItem:
    """Tests for ReviewItem contracts (deliverable 1, AD-033)."""

    def test_review_item_id_generate(self) -> None:
        rid = ReviewItemId.generate()
        assert isinstance(rid, ReviewItemId)
        assert isinstance(rid.value, UUID)

    def test_review_item_id_str(self) -> None:
        rid = ReviewItemId.generate()
        assert str(rid) == str(rid.value)

    def test_review_item_create_pass(self) -> None:
        item = ReviewItem.create(
            category=ReviewCategory.ARCHITECTURE_CONSISTENCY,
            gate=1,
            title="Test item",
            description="Description",
            status=ReviewStatus.PASS,
            evidence="test evidence",
        )
        assert item.status is ReviewStatus.PASS
        assert not item.is_blocking
        assert item.gate == 1

    def test_review_item_create_fail_blocking(self) -> None:
        item = ReviewItem.create(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Security gap",
            description="Description",
            status=ReviewStatus.FAIL,
            evidence="evidence",
            remediation="Fix it",
        )
        assert item.is_blocking
        assert item.remediation == "Fix it"

    def test_review_item_create_warn_not_blocking(self) -> None:
        item = ReviewItem.create(
            category=ReviewCategory.PERFORMANCE,
            gate=4,
            title="Performance warning",
            description="Description",
            status=ReviewStatus.WARN,
            evidence="evidence",
        )
        assert not item.is_blocking
        assert item.status is ReviewStatus.WARN

    def test_review_item_invalid_gate(self) -> None:
        with pytest.raises(ValueError, match="Gate must be 1-5"):
            ReviewItem.create(
                category=ReviewCategory.SECURITY,
                gate=6,
                title="Test",
                description="Description",
                status=ReviewStatus.PASS,
                evidence="evidence",
            )

    def test_review_item_gate_zero(self) -> None:
        with pytest.raises(ValueError, match="Gate must be 1-5"):
            ReviewItem.create(
                category=ReviewCategory.SECURITY,
                gate=0,
                title="Test",
                description="Description",
                status=ReviewStatus.PASS,
                evidence="evidence",
            )

    def test_review_item_reviewed_at_set(self) -> None:
        item = ReviewItem.create(
            category=ReviewCategory.FINANCIAL_CORRECTNESS,
            gate=3,
            title="Test",
            description="Description",
            status=ReviewStatus.PASS,
            evidence="evidence",
        )
        assert item.reviewed_at is not None

    def test_all_review_categories(self) -> None:
        categories = [
            ReviewCategory.ARCHITECTURE_CONSISTENCY,
            ReviewCategory.FINANCIAL_CORRECTNESS,
            ReviewCategory.SECURITY,
            ReviewCategory.PERFORMANCE,
            ReviewCategory.COMPLIANCE,
            ReviewCategory.RELEASE_READINESS,
        ]
        assert len(categories) == 6

    def test_all_review_statuses(self) -> None:
        statuses = [
            ReviewStatus.PASS,
            ReviewStatus.FAIL,
            ReviewStatus.WARN,
            ReviewStatus.NOT_APPLICABLE,
        ]
        assert len(statuses) == 4


class TestDependencyRecord:
    """Tests for DependencyRecord contracts (deliverable 2, AD-024)."""

    def test_dependency_id_generate(self) -> None:
        did = DependencyId.generate()
        assert isinstance(did, DependencyId)
        assert isinstance(did.value, UUID)

    def test_dependency_create_verified(self) -> None:
        dep = DependencyRecord.create(
            name="fastapi",
            version="0.115.0",
            declared_version=">=0.115.0",
            status=DependencyStatus.VERIFIED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
        )
        assert dep.status is DependencyStatus.VERIFIED
        assert not dep.is_blocking

    def test_dependency_vulnerable_blocking(self) -> None:
        dep = DependencyRecord.create(
            name="bad-lib",
            version="1.0.0",
            declared_version=">=1.0.0",
            status=DependencyStatus.VULNERABLE,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
        )
        assert dep.is_blocking

    def test_dependency_incompatible_blocking(self) -> None:
        dep = DependencyRecord.create(
            name="conflict-lib",
            version="1.0.0",
            declared_version=">=1.0.0",
            status=DependencyStatus.VERIFIED,
            is_pinned=True,
            license_type="GPL",
            compatible=False,
        )
        assert dep.is_blocking

    def test_dependency_pinned_status(self) -> None:
        dep = DependencyRecord.create(
            name="pydantic",
            version="2.10.0",
            declared_version=">=2.10.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
        )
        assert dep.status is DependencyStatus.PINNED
        assert not dep.is_blocking

    def test_dependency_unpinned_status(self) -> None:
        dep = DependencyRecord.create(
            name="unpinned-lib",
            version="1.0.0",
            declared_version="*",
            status=DependencyStatus.UNPINNED,
            is_pinned=False,
            license_type="MIT",
            compatible=True,
        )
        assert not dep.is_pinned


class TestReleaseArtifact:
    """Tests for ReleaseArtifact contracts (deliverable 3, AD-024)."""

    def test_artifact_id_generate(self) -> None:
        aid = ArtifactId.generate()
        assert isinstance(aid, ArtifactId)
        assert isinstance(aid.value, UUID)

    def test_artifact_create_verified(self) -> None:
        artifact = ReleaseArtifact.create(
            name="kian-trading-intelligence-0.10.0.tar.gz",
            artifact_type=ArtifactType.PYTHON_PACKAGE,
            version="0.10.0",
            sha256="a" * 64,
            size_bytes=1024000,
        )
        assert artifact.integrity_status is IntegrityStatus.VERIFIED
        assert not artifact.is_blocking

    def test_artifact_sha256_validation(self) -> None:
        with pytest.raises(ValueError, match="SHA-256 must be 64 hex"):
            ReleaseArtifact.create(
                name="test",
                artifact_type=ArtifactType.PYTHON_PACKAGE,
                version="1.0.0",
                sha256="short",
                size_bytes=100,
            )

    def test_artifact_negative_size(self) -> None:
        with pytest.raises(ValueError, match="Size must be non-negative"):
            ReleaseArtifact.create(
                name="test",
                artifact_type=ArtifactType.PYTHON_PACKAGE,
                version="1.0.0",
                sha256="a" * 64,
                size_bytes=-1,
            )

    def test_artifact_mismatch_blocking(self) -> None:
        artifact = ReleaseArtifact.create(
            name="test",
            artifact_type=ArtifactType.FRONTEND_BUNDLE,
            version="1.0.0",
            sha256="b" * 64,
            size_bytes=5000,
            integrity_status=IntegrityStatus.MISMATCH,
        )
        assert artifact.is_blocking

    def test_artifact_missing_blocking(self) -> None:
        artifact = ReleaseArtifact.create(
            name="test",
            artifact_type=ArtifactType.DOCKER_IMAGE,
            version="1.0.0",
            sha256="c" * 64,
            size_bytes=50000,
            integrity_status=IntegrityStatus.MISSING,
        )
        assert artifact.is_blocking

    def test_all_artifact_types(self) -> None:
        types = [
            ArtifactType.PYTHON_PACKAGE,
            ArtifactType.FRONTEND_BUNDLE,
            ArtifactType.DOCKER_IMAGE,
            ArtifactType.MIGRATION_SCRIPT,
            ArtifactType.CONFIGURATION,
            ArtifactType.DOCUMENTATION,
        ]
        assert len(types) == 6


class TestMigrationRecord:
    """Tests for MigrationRecord contracts (deliverable 4, AD-024)."""

    def test_migration_id_generate(self) -> None:
        mid = MigrationId.generate()
        assert isinstance(mid, MigrationId)
        assert isinstance(mid.value, UUID)

    def test_migration_applied(self) -> None:
        migration = MigrationRecord.create(
            version="001",
            description="Create tenants table",
            status=MigrationStatus.APPLIED,
            is_reversible=True,
            rollback_tested=True,
        )
        assert not migration.is_blocking
        assert migration.rollback_tested

    def test_migration_failed_blocking(self) -> None:
        migration = MigrationRecord.create(
            version="002",
            description="Bad migration",
            status=MigrationStatus.FAILED,
            is_reversible=False,
        )
        assert migration.is_blocking

    def test_migration_irreversible_blocking(self) -> None:
        migration = MigrationRecord.create(
            version="003",
            description="Destructive migration",
            status=MigrationStatus.APPLIED,
            is_reversible=False,
        )
        assert migration.is_blocking

    def test_migration_rolled_back(self) -> None:
        migration = MigrationRecord.create(
            version="004",
            description="Rolled back",
            status=MigrationStatus.ROLLED_BACK,
            is_reversible=True,
        )
        assert migration.status is MigrationStatus.ROLLED_BACK

    def test_migration_with_dependency_chain(self) -> None:
        migration = MigrationRecord.create(
            version="005",
            description="Depends on 001 and 002",
            status=MigrationStatus.APPLIED,
            is_reversible=True,
            rollback_tested=True,
            dependency_chain=["001", "002"],
        )
        assert migration.dependency_chain == ["001", "002"]


class TestStagingDeployment:
    """Tests for StagingDeployment contracts (deliverable 5, AD-024)."""

    def test_deployment_id_generate(self) -> None:
        did = DeploymentId.generate()
        assert isinstance(did, DeploymentId)
        assert isinstance(did.value, UUID)

    def test_deployment_create(self) -> None:
        deployment = StagingDeployment.create(
            version="0.10.0",
            environment="staging",
        )
        assert deployment.status is DeploymentStatus.PENDING
        assert not deployment.is_blocking

    def test_deployment_add_health_check_healthy(self) -> None:
        deployment = StagingDeployment.create(version="0.10.0")
        check1 = HealthCheckResult.create(
            endpoint="/health", status_code=200, response_time_ms=50.0
        )
        check2 = HealthCheckResult.create(
            endpoint="/health/ready", status_code=200, response_time_ms=30.0
        )
        deployment.add_health_check(check1)
        deployment.add_health_check(check2)
        assert deployment.all_health_checks_passed
        assert deployment.status is DeploymentStatus.HEALTHY

    def test_deployment_unhealthy_blocking(self) -> None:
        deployment = StagingDeployment.create(version="0.10.0")
        check = HealthCheckResult.create(
            endpoint="/health", status_code=500, response_time_ms=200.0
        )
        deployment.add_health_check(check)
        assert deployment.is_blocking

    def test_health_check_result(self) -> None:
        check = HealthCheckResult.create(endpoint="/health", status_code=200, response_time_ms=50.0)
        assert check.is_healthy

    def test_health_check_unhealthy(self) -> None:
        check = HealthCheckResult.create(
            endpoint="/health", status_code=503, response_time_ms=500.0
        )
        assert not check.is_healthy

    def test_all_deployment_statuses(self) -> None:
        statuses = [
            DeploymentStatus.PENDING,
            DeploymentStatus.DEPLOYING,
            DeploymentStatus.DEPLOYED,
            DeploymentStatus.HEALTHY,
            DeploymentStatus.UNHEALTHY,
            DeploymentStatus.ROLLED_BACK,
            DeploymentStatus.FAILED,
        ]
        assert len(statuses) == 7


class TestCanaryDeployment:
    """Tests for CanaryDeployment contracts (deliverable 6, AD-024)."""

    def test_canary_id_generate(self) -> None:
        cid = CanaryId.generate()
        assert isinstance(cid, CanaryId)
        assert isinstance(cid.value, UUID)

    def test_canary_create(self) -> None:
        canary = CanaryDeployment.create(version="0.10.0")
        assert canary.status is CanaryStatus.PENDING
        assert not canary.is_blocking

    def test_canary_advance_full_progression(self) -> None:
        canary = CanaryDeployment.create(version="0.10.0")
        assert canary.advance() is CanaryStatus.SHADOW
        assert canary.advance() is CanaryStatus.CANARY_10
        assert canary.advance() is CanaryStatus.CANARY_50
        assert canary.advance() is CanaryStatus.CANARY_100
        assert canary.advance() is CanaryStatus.PROMOTED

    def test_canary_advance_aborted_raises(self) -> None:
        canary = CanaryDeployment.create(version="0.10.0")
        # Force abort by setting bad metrics
        metrics = CanaryMetrics.create(
            error_rate=0.5,
            latency_p95_ms=1000.0,
            latency_p99_ms=2000.0,
            throughput_per_sec=10.0,
            sample_count=100,
        )
        canary.set_metrics(metrics)
        assert canary.status is CanaryStatus.ABORTED
        assert canary.is_blocking
        with pytest.raises(PermissionError, match="Cannot advance an aborted"):
            canary.advance()

    def test_canary_advance_promoted_raises(self) -> None:
        canary = CanaryDeployment.create(version="0.10.0")
        canary.advance()
        canary.advance()
        canary.advance()
        canary.advance()
        canary.advance()
        assert canary.status is CanaryStatus.PROMOTED
        with pytest.raises(PermissionError, match="Cannot advance a promoted"):
            canary.advance()

    def test_canary_metrics_within_targets(self) -> None:
        metrics = CanaryMetrics.create(
            error_rate=0.001,
            latency_p95_ms=200.0,
            latency_p99_ms=80.0,
            throughput_per_sec=100.0,
            sample_count=1000,
        )
        assert metrics.within_targets

    def test_canary_metrics_outside_targets(self) -> None:
        metrics = CanaryMetrics.create(
            error_rate=0.02,
            latency_p95_ms=600.0,
            latency_p99_ms=150.0,
            throughput_per_sec=50.0,
            sample_count=100,
        )
        assert not metrics.within_targets

    def test_canary_metrics_error_rate_validation(self) -> None:
        with pytest.raises(ValueError, match="Error rate must be 0.0-1.0"):
            CanaryMetrics.create(
                error_rate=1.5,
                latency_p95_ms=100.0,
                latency_p99_ms=50.0,
                throughput_per_sec=100.0,
                sample_count=100,
            )

    def test_canary_set_good_metrics(self) -> None:
        canary = CanaryDeployment.create(version="0.10.0")
        metrics = CanaryMetrics.create(
            error_rate=0.001,
            latency_p95_ms=250.0,
            latency_p99_ms=90.0,
            throughput_per_sec=200.0,
            sample_count=5000,
        )
        canary.set_metrics(metrics)
        assert canary.status is not CanaryStatus.ABORTED
        assert canary.metrics is not None


class TestRollbackTest:
    """Tests for RollbackTest contracts (deliverable 7, AD-024)."""

    def test_rollback_id_generate(self) -> None:
        rid = RollbackId.generate()
        assert isinstance(rid, RollbackId)
        assert isinstance(rid.value, UUID)

    def test_rollback_create(self) -> None:
        test = RollbackTest.create(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        assert test.status is RollbackStatus.PENDING
        assert not test.is_blocking

    def test_rollback_complete_verified(self) -> None:
        test = RollbackTest.create(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        test.complete(
            data_integrity_verified=True,
            financial_effects_preserved=True,
        )
        assert test.status is RollbackStatus.VERIFIED
        assert not test.is_blocking
        assert test.completed_at is not None
        assert test.duration is not None

    def test_rollback_complete_partial(self) -> None:
        test = RollbackTest.create(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        test.complete(
            data_integrity_verified=True,
            financial_effects_preserved=False,
        )
        assert test.status is RollbackStatus.PARTIAL
        assert test.is_blocking

    def test_rollback_financial_effects_not_preserved_blocking(self) -> None:
        test = RollbackTest.create(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        test.complete(
            data_integrity_verified=False,
            financial_effects_preserved=False,
        )
        assert test.is_blocking

    def test_rollback_duration_calculated(self) -> None:
        test = RollbackTest.create(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        test.complete(
            data_integrity_verified=True,
            financial_effects_preserved=True,
        )
        assert test.duration is not None
        assert test.duration >= timedelta(0)


class TestOperationalRunbook:
    """Tests for OperationalRunbook contracts (deliverable 8, AD-017, AD-028)."""

    def test_runbook_id_generate(self) -> None:
        rid = RunbookId.generate()
        assert isinstance(rid, RunbookId)
        assert isinstance(rid.value, UUID)

    def test_runbook_create(self) -> None:
        steps = [
            RunbookStep(
                step_number=1,
                action="Detect failure",
                expected_result="Failure detected",
            ),
            RunbookStep(
                step_number=2,
                action="Isolate systems",
                expected_result="Isolated",
                requires_human_approval=True,
            ),
        ]
        runbook = OperationalRunbook.create(
            category=RunbookCategory.EMERGENCY_STOP,
            title="Emergency Stop",
            description="Stop procedure",
            steps=steps,
        )
        assert len(runbook.steps) == 2
        assert runbook.has_human_gate
        assert not runbook.is_blocking

    def test_runbook_empty_steps_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one step"):
            OperationalRunbook.create(
                category=RunbookCategory.DEPLOYMENT,
                title="Test",
                description="Test",
                steps=[],
            )

    def test_runbook_step_number_validation(self) -> None:
        with pytest.raises(ValueError, match="sequentially numbered"):
            OperationalRunbook.create(
                category=RunbookCategory.ROLLBACK,
                title="Test",
                description="Test",
                steps=[
                    RunbookStep(
                        step_number=2,
                        action="First",
                        expected_result="First",
                    ),
                ],
            )

    def test_runbook_step_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Step number must be >= 1"):
            RunbookStep(
                step_number=0,
                action="Zero",
                expected_result="Zero",
            )

    def test_runbook_all_categories(self) -> None:
        categories = [
            RunbookCategory.EMERGENCY_STOP,
            RunbookCategory.DISASTER_RECOVERY,
            RunbookCategory.SPLIT_BRAIN,
            RunbookCategory.FINANCIAL_RECONCILIATION,
            RunbookCategory.SECURITY_INCIDENT,
            RunbookCategory.DEPLOYMENT,
            RunbookCategory.ROLLBACK,
            RunbookCategory.LIVE_ACTIVATION,
        ]
        assert len(categories) == 8

    def test_runbook_human_gate_detection(self) -> None:
        steps = [
            RunbookStep(
                step_number=1,
                action="Auto step",
                expected_result="Auto",
                requires_human_approval=False,
            ),
        ]
        runbook = OperationalRunbook.create(
            category=RunbookCategory.DEPLOYMENT,
            title="Test",
            description="Test",
            steps=steps,
            human_approval_required=False,
        )
        assert not runbook.has_human_gate

    def test_runbook_human_gate_required_flag(self) -> None:
        steps = [
            RunbookStep(
                step_number=1,
                action="Auto step",
                expected_result="Auto",
                requires_human_approval=False,
            ),
        ]
        runbook = OperationalRunbook.create(
            category=RunbookCategory.EMERGENCY_STOP,
            title="Test",
            description="Test",
            steps=steps,
            human_approval_required=True,
        )
        assert runbook.has_human_gate


class TestDocumentationRecord:
    """Tests for DocumentationRecord contracts (deliverables 9, 10)."""

    def test_doc_id_generate(self) -> None:
        did = DocId.generate()
        assert isinstance(did, DocId)
        assert isinstance(did.value, UUID)

    def test_doc_create(self) -> None:
        doc = DocumentationRecord.create(
            doc_type=DocType.USER_GUIDE,
            title="User Guide",
            path="docs/user-guide.md",
            status=DocStatus.REVIEWED,
            sections=10,
            word_count=3500,
        )
        assert not doc.is_blocking

    def test_doc_missing_blocking(self) -> None:
        doc = DocumentationRecord.create(
            doc_type=DocType.ADMIN_GUIDE,
            title="Missing Guide",
            path="docs/missing.md",
            status=DocStatus.MISSING,
        )
        assert doc.is_blocking

    def test_doc_outdated_blocking(self) -> None:
        doc = DocumentationRecord.create(
            doc_type=DocType.API_REFERENCE,
            title="Outdated API",
            path="docs/old-api.md",
            status=DocStatus.OUTDATED,
        )
        assert doc.is_blocking

    def test_doc_negative_sections_raises(self) -> None:
        with pytest.raises(ValueError, match="Sections must be non-negative"):
            DocumentationRecord.create(
                doc_type=DocType.USER_GUIDE,
                title="Test",
                path="test",
                status=DocStatus.DRAFT,
                sections=-1,
            )

    def test_doc_negative_word_count_raises(self) -> None:
        with pytest.raises(ValueError, match="Word count must be non-negative"):
            DocumentationRecord.create(
                doc_type=DocType.USER_GUIDE,
                title="Test",
                path="test",
                status=DocStatus.DRAFT,
                word_count=-100,
            )

    def test_all_doc_types(self) -> None:
        types = [
            DocType.USER_GUIDE,
            DocType.ADMIN_GUIDE,
            DocType.API_REFERENCE,
            DocType.ARCHITECTURE_DOC,
            DocType.RUNBOOK,
            DocType.RELEASE_NOTES,
            DocType.COMPLIANCE_DOC,
        ]
        assert len(types) == 7


class TestReleaseEvidencePackage:
    """Tests for ReleaseEvidencePackage contracts (deliverable 11, AD-032)."""

    def test_evidence_id_generate(self) -> None:
        eid = EvidenceId.generate()
        assert isinstance(eid, EvidenceId)
        assert isinstance(eid.value, UUID)

    def test_evidence_record_create(self) -> None:
        record = EvidenceRecord.create(
            evidence_type=EvidenceType.TEST_RESULTS,
            component="pytest",
            command="pytest -v",
            expected_result="933 passed",
            observed_result="933 passed",
            passed=True,
        )
        assert record.passed

    def test_evidence_package_add(self) -> None:
        pkg = ReleaseEvidencePackage(release_version="0.10.0")
        record = EvidenceRecord.create(
            evidence_type=EvidenceType.TEST_RESULTS,
            component="pytest",
            command="pytest -v",
            expected_result="all pass",
            observed_result="all pass",
            passed=True,
        )
        pkg.add_evidence(record)
        assert pkg.total_count == 1
        assert pkg.all_passed

    def test_evidence_package_failed_count(self) -> None:
        pkg = ReleaseEvidencePackage(release_version="0.10.0")
        r1 = EvidenceRecord.create(
            evidence_type=EvidenceType.TEST_RESULTS,
            component="pytest",
            command="pytest -v",
            expected_result="all pass",
            observed_result="all pass",
            passed=True,
        )
        r2 = EvidenceRecord.create(
            evidence_type=EvidenceType.SECURITY_SCAN,
            component="secret-scan",
            command="pytest tests/test_secret_scan.py",
            expected_result="0 findings",
            observed_result="2 findings",
            passed=False,
        )
        pkg.add_evidence(r1)
        pkg.add_evidence(r2)
        assert pkg.failed_count == 1
        assert not pkg.all_passed

    def test_evidence_package_coverage(self) -> None:
        pkg = ReleaseEvidencePackage(release_version="0.10.0")
        types = [
            EvidenceType.TEST_RESULTS,
            EvidenceType.SECURITY_SCAN,
            EvidenceType.FINANCIAL_SAFETY,
            EvidenceType.PERFORMANCE_BENCHMARK,
            EvidenceType.COMPLIANCE_CHECK,
            EvidenceType.MIGRATION_VERIFICATION,
            EvidenceType.ROLLBACK_VERIFICATION,
            EvidenceType.ARCHITECTURE_REVIEW,
            EvidenceType.DEPLOYMENT_EVIDENCE,
        ]
        for et in types:
            pkg.add_evidence(
                EvidenceRecord.create(
                    evidence_type=et,
                    component="test",
                    command="test",
                    expected_result="pass",
                    observed_result="pass",
                    passed=True,
                )
            )
        assert pkg.is_complete

    def test_evidence_package_incomplete(self) -> None:
        pkg = ReleaseEvidencePackage(release_version="0.10.0")
        pkg.add_evidence(
            EvidenceRecord.create(
                evidence_type=EvidenceType.TEST_RESULTS,
                component="pytest",
                command="pytest",
                expected_result="pass",
                observed_result="pass",
                passed=True,
            )
        )
        assert not pkg.is_complete

    def test_evidence_package_with_failing_not_complete(self) -> None:
        pkg = ReleaseEvidencePackage(release_version="0.10.0")
        types = [
            EvidenceType.TEST_RESULTS,
            EvidenceType.SECURITY_SCAN,
            EvidenceType.FINANCIAL_SAFETY,
            EvidenceType.PERFORMANCE_BENCHMARK,
            EvidenceType.COMPLIANCE_CHECK,
            EvidenceType.MIGRATION_VERIFICATION,
            EvidenceType.ROLLBACK_VERIFICATION,
            EvidenceType.ARCHITECTURE_REVIEW,
            EvidenceType.DEPLOYMENT_EVIDENCE,
        ]
        for i, et in enumerate(types):
            pkg.add_evidence(
                EvidenceRecord.create(
                    evidence_type=et,
                    component="test",
                    command="test",
                    expected_result="pass",
                    observed_result="pass" if i != 0 else "fail",
                    passed=i != 0,
                )
            )
        assert not pkg.is_complete

    def test_evidence_package_empty(self) -> None:
        pkg = ReleaseEvidencePackage(release_version="0.10.0")
        assert not pkg.all_passed
        assert not pkg.is_complete
        assert pkg.total_count == 0

    def test_all_evidence_types(self) -> None:
        types = [
            EvidenceType.TEST_RESULTS,
            EvidenceType.SECURITY_SCAN,
            EvidenceType.FINANCIAL_SAFETY,
            EvidenceType.PERFORMANCE_BENCHMARK,
            EvidenceType.MIGRATION_VERIFICATION,
            EvidenceType.ROLLBACK_VERIFICATION,
            EvidenceType.ARCHITECTURE_REVIEW,
            EvidenceType.DEPLOYMENT_EVIDENCE,
            EvidenceType.COMPLIANCE_CHECK,
        ]
        assert len(types) == 9


class TestFinalReadinessReport:
    """Tests for FinalReadinessReport contracts (deliverable 12, AD-033)."""

    def test_report_id_generate(self) -> None:
        rid = ReadinessReportId.generate()
        assert isinstance(rid, ReadinessReportId)
        assert isinstance(rid.value, UUID)

    def test_gate_result_validation(self) -> None:
        with pytest.raises(ValueError, match="Gate number must be 1-5"):
            GateResult(
                gate_number=6,
                gate_name="Invalid",
                passed=True,
                evidence_count=0,
            )

    def test_report_create_all_passed(self) -> None:
        gates = [
            GateResult(
                gate_number=1,
                gate_name="Functional Correctness",
                passed=True,
                evidence_count=10,
            ),
            GateResult(
                gate_number=2,
                gate_name="Security",
                passed=True,
                evidence_count=5,
            ),
            GateResult(
                gate_number=3,
                gate_name="Financial Safety",
                passed=True,
                evidence_count=5,
            ),
            GateResult(
                gate_number=4,
                gate_name="Performance and Reliability",
                passed=True,
                evidence_count=4,
            ),
            GateResult(
                gate_number=5,
                gate_name="Controlled Live Readiness",
                passed=True,
                evidence_count=6,
            ),
        ]
        report = FinalReadinessReport.create(
            release_version="0.10.0",
            decision=ReadinessDecision.GO,
            gates=gates,
        )
        assert report.all_gates_passed
        assert report.is_go
        assert not report.can_activate_live

    def test_report_with_live_authorized(self) -> None:
        gates = [
            GateResult(
                gate_number=i + 1,
                gate_name=f"Gate {i + 1}",
                passed=True,
                evidence_count=1,
            )
            for i in range(5)
        ]
        report = FinalReadinessReport.create(
            release_version="0.10.0",
            decision=ReadinessDecision.GO,
            gates=gates,
        )
        report.live_authorized = True
        assert report.can_activate_live

    def test_report_no_go_with_blocking(self) -> None:
        gates = [
            GateResult(
                gate_number=1,
                gate_name="Functional Correctness",
                passed=True,
                evidence_count=5,
            ),
            GateResult(
                gate_number=2,
                gate_name="Security",
                passed=False,
                evidence_count=2,
            ),
            GateResult(
                gate_number=3,
                gate_name="Financial Safety",
                passed=True,
                evidence_count=3,
            ),
            GateResult(
                gate_number=4,
                gate_name="Performance",
                passed=True,
                evidence_count=3,
            ),
            GateResult(
                gate_number=5,
                gate_name="Live Readiness",
                passed=True,
                evidence_count=3,
            ),
        ]
        report = FinalReadinessReport.create(
            release_version="0.10.0",
            decision=ReadinessDecision.NO_GO,
            gates=gates,
            blocking_items=["Security gate failed"],
        )
        assert not report.all_gates_passed
        assert not report.is_go
        assert not report.can_activate_live

    def test_report_empty_gates_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one gate"):
            FinalReadinessReport.create(
                release_version="0.10.0",
                decision=ReadinessDecision.GO,
                gates=[],
            )

    def test_report_conditional_go(self) -> None:
        gates = [
            GateResult(
                gate_number=i + 1,
                gate_name=f"Gate {i + 1}",
                passed=True,
                evidence_count=1,
            )
            for i in range(5)
        ]
        report = FinalReadinessReport.create(
            release_version="0.10.0",
            decision=ReadinessDecision.CONDITIONAL_GO,
            gates=gates,
            blocking_items=["Compliance review pending"],
        )
        assert report.all_gates_passed
        assert not report.is_go
        assert len(report.blocking_items) == 1

    def test_report_live_not_authorized_by_default(self) -> None:
        """Per Section 17 PHASE 10: completion does not authorize live trading."""
        gates = [
            GateResult(
                gate_number=i + 1,
                gate_name=f"Gate {i + 1}",
                passed=True,
                evidence_count=1,
            )
            for i in range(5)
        ]
        report = FinalReadinessReport.create(
            release_version="0.10.0",
            decision=ReadinessDecision.GO,
            gates=gates,
        )
        assert not report.live_authorized
        assert not report.can_activate_live

    def test_report_mining_not_authorized_by_default(self) -> None:
        """Per Section 17 PHASE 10: completion does not authorize mining."""
        gates = [
            GateResult(
                gate_number=i + 1,
                gate_name=f"Gate {i + 1}",
                passed=True,
                evidence_count=1,
            )
            for i in range(5)
        ]
        report = FinalReadinessReport.create(
            release_version="0.10.0",
            decision=ReadinessDecision.GO,
            gates=gates,
        )
        assert not report.mining_authorized

    def test_all_readiness_decisions(self) -> None:
        decisions = [
            ReadinessDecision.GO,
            ReadinessDecision.NO_GO,
            ReadinessDecision.CONDITIONAL_GO,
        ]
        assert len(decisions) == 3
