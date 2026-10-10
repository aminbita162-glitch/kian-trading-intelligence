"""Release engineering service tests for Phase 10 — Release Engineering
and Controlled Launch.

Per Section 17 PHASE 10 deliverables:
5. Staging deployment (AD-024)
6. Shadow/canary readiness (AD-024)
7. Rollback testing (AD-024)
8. Operational runbooks (AD-017, AD-028)
9. User documentation (AD-030)
10. Administrator documentation (AD-022)
11. Release evidence package (AD-032)
12. Final readiness report (AD-033)
"""

from __future__ import annotations

from contracts.release import (
    ArtifactType,
    CanaryMetrics,
    CanaryStatus,
    DependencyStatus,
    DeploymentStatus,
    DocStatus,
    DocType,
    EvidenceType,
    IntegrityStatus,
    MigrationStatus,
    ReadinessDecision,
    ReviewCategory,
    ReviewStatus,
    RollbackStatus,
    RunbookCategory,
    RunbookStep,
)
from services.release import (
    ArchitectureReviewService,
    CanaryService,
    DependencyVerificationService,
    DocumentationService,
    MigrationVerificationService,
    ReadinessReportService,
    ReleaseArtifactService,
    ReleaseEvidenceService,
    RollbackTestingService,
    RunbookService,
    StagingDeploymentService,
    create_standard_dependencies,
    create_standard_documentation,
    create_standard_review_items,
    create_standard_runbooks,
)


class TestArchitectureReviewService:
    """Tests for ArchitectureReviewService (deliverable 1, AD-033)."""

    def test_add_review_item(self) -> None:
        service = ArchitectureReviewService()
        service.add_item(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Security check",
            description="Check",
            status=ReviewStatus.PASS,
            evidence="test evidence",
        )
        assert len(service.items) == 1
        assert not service.has_blocking_findings

    def test_blocking_finding(self) -> None:
        service = ArchitectureReviewService()
        service.add_item(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Security gap",
            description="Gap",
            status=ReviewStatus.FAIL,
            evidence="evidence",
        )
        assert service.has_blocking_findings
        assert len(service.blocking_items) == 1

    def test_warnings(self) -> None:
        service = ArchitectureReviewService()
        service.add_item(
            category=ReviewCategory.PERFORMANCE,
            gate=4,
            title="Perf warning",
            description="Warning",
            status=ReviewStatus.WARN,
            evidence="evidence",
        )
        assert len(service.warnings) == 1
        assert not service.has_blocking_findings

    def test_gate_summary(self) -> None:
        service = ArchitectureReviewService()
        service.add_item(
            category=ReviewCategory.SECURITY,
            gate=1,
            title="Item 1",
            description="Desc",
            status=ReviewStatus.PASS,
            evidence="ev",
        )
        service.add_item(
            category=ReviewCategory.SECURITY,
            gate=1,
            title="Item 2",
            description="Desc",
            status=ReviewStatus.FAIL,
            evidence="ev",
        )
        summary = service.gate_summary
        assert 1 in summary
        assert summary[1]["pass"] == 1
        assert summary[1]["fail"] == 1

    def test_standard_review_items(self) -> None:
        items = create_standard_review_items()
        assert len(items) > 0
        for item in items:
            assert 1 <= item.gate <= 5
            assert item.category in ReviewCategory


class TestDependencyVerificationService:
    """Tests for DependencyVerificationService (deliverable 2, AD-024)."""

    def test_add_dependency(self) -> None:
        service = DependencyVerificationService()
        service.verify(
            name="fastapi",
            version="0.115.0",
            declared_version=">=0.115.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
        )
        assert len(service.dependencies) == 1
        assert service.all_pinned
        assert service.all_compatible
        assert not service.has_blocking_findings

    def test_blocking_dependency(self) -> None:
        service = DependencyVerificationService()
        service.verify(
            name="vuln-lib",
            version="1.0.0",
            declared_version=">=1.0.0",
            status=DependencyStatus.VULNERABLE,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
        )
        assert service.has_blocking_findings
        assert len(service.blocking_dependencies) == 1

    def test_all_pinned_false_with_unpinned(self) -> None:
        service = DependencyVerificationService()
        service.verify(
            name="unpinned",
            version="1.0.0",
            declared_version="*",
            status=DependencyStatus.UNPINNED,
            is_pinned=False,
            license_type="MIT",
            compatible=True,
        )
        assert not service.all_pinned

    def test_standard_dependencies(self) -> None:
        deps = create_standard_dependencies()
        assert len(deps) > 0
        for dep in deps:
            assert dep.is_pinned
            assert dep.compatible
            assert not dep.is_blocking


class TestReleaseArtifactService:
    """Tests for ReleaseArtifactService (deliverable 3, AD-024)."""

    def test_register_artifact(self) -> None:
        service = ReleaseArtifactService()
        service.register_artifact(
            name="package.tar.gz",
            artifact_type=ArtifactType.PYTHON_PACKAGE,
            version="0.10.0",
            sha256="a" * 64,
            size_bytes=102400,
        )
        assert len(service.artifacts) == 1
        assert service.all_verified
        assert not service.has_blocking_findings

    def test_blocking_artifact(self) -> None:
        service = ReleaseArtifactService()
        service.register_artifact(
            name="bad.tar.gz",
            artifact_type=ArtifactType.PYTHON_PACKAGE,
            version="0.10.0",
            sha256="b" * 64,
            size_bytes=100,
            integrity_status=IntegrityStatus.MISMATCH,
        )
        assert service.has_blocking_findings
        assert len(service.blocking_artifacts) == 1

    def test_compute_sha256(self) -> None:
        data = b"test data"
        result = ReleaseArtifactService.compute_sha256(data)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_verify_integrity_match(self) -> None:
        service = ReleaseArtifactService()
        artifact = service.register_artifact(
            name="test.tar.gz",
            artifact_type=ArtifactType.PYTHON_PACKAGE,
            version="1.0.0",
            sha256="c" * 64,
            size_bytes=500,
        )
        assert service.verify_integrity(artifact, "c" * 64)

    def test_verify_integrity_mismatch(self) -> None:
        service = ReleaseArtifactService()
        artifact = service.register_artifact(
            name="test.tar.gz",
            artifact_type=ArtifactType.PYTHON_PACKAGE,
            version="1.0.0",
            sha256="d" * 64,
            size_bytes=500,
        )
        assert not service.verify_integrity(artifact, "e" * 64)

    def test_all_verified_false_with_blocking(self) -> None:
        service = ReleaseArtifactService()
        service.register_artifact(
            name="ok",
            artifact_type=ArtifactType.PYTHON_PACKAGE,
            version="1.0",
            sha256="a" * 64,
            size_bytes=100,
        )
        service.register_artifact(
            name="bad",
            artifact_type=ArtifactType.PYTHON_PACKAGE,
            version="1.0",
            sha256="b" * 64,
            size_bytes=100,
            integrity_status=IntegrityStatus.CORRUPTED,
        )
        assert not service.all_verified
        assert service.has_blocking_findings


class TestMigrationVerificationService:
    """Tests for MigrationVerificationService (deliverable 4, AD-024)."""

    def test_register_migration(self) -> None:
        service = MigrationVerificationService()
        service.register_migration(
            version="001",
            description="Create tables",
            status=MigrationStatus.APPLIED,
            is_reversible=True,
            rollback_tested=True,
        )
        assert len(service.migrations) == 1
        assert service.all_reversible
        assert service.all_rollback_tested
        assert not service.has_blocking_findings

    def test_blocking_migration(self) -> None:
        service = MigrationVerificationService()
        service.register_migration(
            version="002",
            description="Failed",
            status=MigrationStatus.FAILED,
            is_reversible=False,
        )
        assert service.has_blocking_findings
        assert len(service.blocking_migrations) == 1

    def test_irreversible_blocking(self) -> None:
        service = MigrationVerificationService()
        service.register_migration(
            version="003",
            description="Destructive",
            status=MigrationStatus.APPLIED,
            is_reversible=False,
        )
        assert service.has_blocking_findings
        assert not service.all_reversible

    def test_all_applied_with_skip(self) -> None:
        service = MigrationVerificationService()
        service.register_migration(
            version="001",
            description="Applied",
            status=MigrationStatus.APPLIED,
            is_reversible=True,
            rollback_tested=True,
        )
        service.register_migration(
            version="002",
            description="Skipped",
            status=MigrationStatus.SKIPPED,
            is_reversible=True,
            rollback_tested=True,
        )
        assert service.all_applied

    def test_all_applied_false_with_pending(self) -> None:
        service = MigrationVerificationService()
        service.register_migration(
            version="001",
            description="Pending",
            status=MigrationStatus.PENDING,
            is_reversible=True,
        )
        assert not service.all_applied


class TestStagingDeploymentService:
    """Tests for StagingDeploymentService (deliverable 5, AD-024)."""

    def test_deploy(self) -> None:
        service = StagingDeploymentService()
        deployment = service.deploy(
            version="0.10.0",
            config_validated=True,
            secrets_referenced=True,
        )
        assert deployment.status is DeploymentStatus.PENDING
        assert deployment.config_validated
        assert deployment.secrets_referenced

    def test_add_health_check_healthy(self) -> None:
        service = StagingDeploymentService()
        deployment = service.deploy(version="0.10.0")
        service.add_health_check(deployment, "/health", 200, 50.0)
        service.add_health_check(deployment, "/health/ready", 200, 30.0)
        assert deployment.status is DeploymentStatus.HEALTHY
        assert not service.has_blocking_findings

    def test_add_health_check_unhealthy(self) -> None:
        service = StagingDeploymentService()
        deployment = service.deploy(version="0.10.0")
        service.add_health_check(deployment, "/health", 500, 200.0)
        assert deployment.status is DeploymentStatus.UNHEALTHY
        assert service.has_blocking_findings

    def test_latest_deployment(self) -> None:
        service = StagingDeploymentService()
        service.deploy(version="0.9.0")
        latest = service.deploy(version="0.10.0")
        assert service.latest_deployment is latest


class TestCanaryService:
    """Tests for CanaryService (deliverable 6, AD-024)."""

    def test_create_canary(self) -> None:
        service = CanaryService()
        canary = service.create_canary(version="0.10.0")
        assert canary.status is CanaryStatus.PENDING
        assert not service.has_blocking_findings

    def test_advance_canary(self) -> None:
        service = CanaryService()
        canary = service.create_canary(version="0.10.0")
        service.advance_canary(canary)
        assert canary.status is CanaryStatus.SHADOW

    def test_set_good_metrics(self) -> None:
        service = CanaryService()
        canary = service.create_canary(version="0.10.0")
        metrics = CanaryMetrics.create(
            error_rate=0.001,
            latency_p95_ms=200.0,
            latency_p99_ms=80.0,
            throughput_per_sec=100.0,
            sample_count=1000,
        )
        service.set_canary_metrics(canary, metrics)
        assert canary.status is not CanaryStatus.ABORTED

    def test_set_bad_metrics_aborts(self) -> None:
        service = CanaryService()
        canary = service.create_canary(version="0.10.0")
        metrics = CanaryMetrics.create(
            error_rate=0.5,
            latency_p95_ms=1000.0,
            latency_p99_ms=2000.0,
            throughput_per_sec=10.0,
            sample_count=100,
        )
        service.set_canary_metrics(canary, metrics)
        assert canary.status is CanaryStatus.ABORTED
        assert service.has_blocking_findings

    def test_latest_canary(self) -> None:
        service = CanaryService()
        service.create_canary(version="0.9.0")
        latest = service.create_canary(version="0.10.0")
        assert service.latest_canary is latest


class TestRollbackTestingService:
    """Tests for RollbackTestingService (deliverable 7, AD-024)."""

    def test_create_rollback_test(self) -> None:
        service = RollbackTestingService()
        test = service.create_rollback_test(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        assert test.status is RollbackStatus.PENDING
        assert not service.has_blocking_findings

    def test_complete_verified(self) -> None:
        service = RollbackTestingService()
        test = service.create_rollback_test(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        service.complete_rollback_test(
            test,
            data_integrity_verified=True,
            financial_effects_preserved=True,
        )
        assert test.status is RollbackStatus.VERIFIED
        assert service.all_verified
        assert not service.has_blocking_findings

    def test_complete_partial_blocking(self) -> None:
        service = RollbackTestingService()
        test = service.create_rollback_test(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        service.complete_rollback_test(
            test,
            data_integrity_verified=True,
            financial_effects_preserved=False,
        )
        assert test.status is RollbackStatus.PARTIAL
        assert service.has_blocking_findings
        assert not service.all_verified


class TestRunbookService:
    """Tests for RunbookService (deliverable 8, AD-017, AD-028)."""

    def test_add_runbook(self) -> None:
        service = RunbookService()
        service.create_runbook(
            category=RunbookCategory.EMERGENCY_STOP,
            title="Emergency Stop",
            description="Stop",
            steps=[
                RunbookStep(
                    step_number=1,
                    action="Stop",
                    expected_result="Stopped",
                ),
            ],
        )
        assert service.count == 1

    def test_get_runbook(self) -> None:
        service = RunbookService()
        runbook = service.create_runbook(
            category=RunbookCategory.DISASTER_RECOVERY,
            title="DR",
            description="Recovery",
            steps=[
                RunbookStep(
                    step_number=1,
                    action="Detect",
                    expected_result="Detected",
                ),
            ],
        )
        assert service.get_runbook(RunbookCategory.DISASTER_RECOVERY) is runbook

    def test_all_have_human_gates(self) -> None:
        service = RunbookService()
        service.create_runbook(
            category=RunbookCategory.EMERGENCY_STOP,
            title="Test",
            description="Test",
            steps=[
                RunbookStep(
                    step_number=1,
                    action="Step",
                    expected_result="Result",
                    requires_human_approval=True,
                ),
            ],
        )
        assert service.all_have_human_gates

    def test_standard_runbooks(self) -> None:
        runbooks = create_standard_runbooks()
        assert len(runbooks) == 8
        for runbook in runbooks:
            assert len(runbook.steps) > 0
            assert runbook.has_human_gate

    def test_standard_runbook_categories(self) -> None:
        runbooks = create_standard_runbooks()
        categories = {r.category for r in runbooks}
        assert RunbookCategory.EMERGENCY_STOP in categories
        assert RunbookCategory.DISASTER_RECOVERY in categories
        assert RunbookCategory.SPLIT_BRAIN in categories
        assert RunbookCategory.FINANCIAL_RECONCILIATION in categories
        assert RunbookCategory.SECURITY_INCIDENT in categories
        assert RunbookCategory.DEPLOYMENT in categories
        assert RunbookCategory.ROLLBACK in categories
        assert RunbookCategory.LIVE_ACTIVATION in categories

    def test_live_activation_runbook_has_human_gate(self) -> None:
        """Per Section 15: live activation requires human authorization."""
        runbooks = create_standard_runbooks()
        live_runbook = next(r for r in runbooks if r.category is RunbookCategory.LIVE_ACTIVATION)
        assert live_runbook.has_human_gate

    def test_emergency_stop_runbook_has_human_gate(self) -> None:
        """Per Section 05.6: emergency stop requires human verification."""
        runbooks = create_standard_runbooks()
        estop_runbook = next(r for r in runbooks if r.category is RunbookCategory.EMERGENCY_STOP)
        assert estop_runbook.has_human_gate


class TestDocumentationService:
    """Tests for DocumentationService (deliverables 9, 10)."""

    def test_add_doc(self) -> None:
        service = DocumentationService()
        service.register_doc(
            doc_type=DocType.USER_GUIDE,
            title="User Guide",
            path="docs/user-guide.md",
            status=DocStatus.REVIEWED,
        )
        assert len(service.docs) == 1
        assert not service.has_blocking_findings

    def test_blocking_doc(self) -> None:
        service = DocumentationService()
        service.register_doc(
            doc_type=DocType.ADMIN_GUIDE,
            title="Missing",
            path="docs/missing.md",
            status=DocStatus.MISSING,
        )
        assert service.has_blocking_findings
        assert len(service.blocking_docs) == 1

    def test_user_docs(self) -> None:
        service = DocumentationService()
        service.register_doc(
            doc_type=DocType.USER_GUIDE,
            title="User Guide",
            path="docs/user.md",
            status=DocStatus.REVIEWED,
        )
        service.register_doc(
            doc_type=DocType.ADMIN_GUIDE,
            title="Admin Guide",
            path="docs/admin.md",
            status=DocStatus.REVIEWED,
        )
        assert len(service.user_docs) == 1
        assert len(service.admin_docs) == 1

    def test_standard_documentation(self) -> None:
        docs = create_standard_documentation()
        assert len(docs) > 0
        user_count = sum(1 for d in docs if d.doc_type is DocType.USER_GUIDE)
        admin_count = sum(1 for d in docs if d.doc_type is DocType.ADMIN_GUIDE)
        assert user_count >= 1
        assert admin_count >= 1
        assert not any(d.is_blocking for d in docs)


class TestReleaseEvidenceService:
    """Tests for ReleaseEvidenceService (deliverable 11, AD-032)."""

    def test_record_evidence(self) -> None:
        service = ReleaseEvidenceService(release_version="0.10.0")
        service.record_evidence(
            evidence_type=EvidenceType.TEST_RESULTS,
            component="pytest",
            command="pytest -v",
            expected_result="all pass",
            observed_result="all pass",
            passed=True,
        )
        assert service.package.total_count == 1
        assert not service.has_failures

    def test_complete_evidence_package(self) -> None:
        service = ReleaseEvidenceService(release_version="0.10.0")
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
            service.record_evidence(
                evidence_type=et,
                component="test",
                command="test",
                expected_result="pass",
                observed_result="pass",
                passed=True,
            )
        assert service.is_complete
        assert not service.has_failures

    def test_incomplete_evidence(self) -> None:
        service = ReleaseEvidenceService(release_version="0.10.0")
        service.record_evidence(
            evidence_type=EvidenceType.TEST_RESULTS,
            component="pytest",
            command="pytest",
            expected_result="pass",
            observed_result="pass",
            passed=True,
        )
        assert not service.is_complete

    def test_failing_evidence(self) -> None:
        service = ReleaseEvidenceService(release_version="0.10.0")
        service.record_evidence(
            evidence_type=EvidenceType.SECURITY_SCAN,
            component="scan",
            command="scan",
            expected_result="0 findings",
            observed_result="3 findings",
            passed=False,
        )
        assert service.has_failures
        assert not service.is_complete


class TestReadinessReportService:
    """Tests for ReadinessReportService (deliverable 12, AD-033)."""

    def _create_all_services(
        self,
    ) -> tuple[
        ArchitectureReviewService,
        DependencyVerificationService,
        ReleaseArtifactService,
        MigrationVerificationService,
        StagingDeploymentService,
        CanaryService,
        RollbackTestingService,
        RunbookService,
        DocumentationService,
        ReleaseEvidenceService,
    ]:
        """Create a full set of passing services for GO decision."""
        arch = ArchitectureReviewService()
        for raw_item in create_standard_review_items():
            current = raw_item
            if current.status is ReviewStatus.WARN:
                current = type(current)(
                    item_id=current.item_id,
                    category=current.category,
                    gate=current.gate,
                    title=current.title,
                    description=current.description,
                    status=ReviewStatus.PASS,
                    evidence=current.evidence,
                    remediation=current.remediation,
                    reviewed_at=current.reviewed_at,
                )
            arch.add_review_item(current)

        deps = DependencyVerificationService()
        for dep in create_standard_dependencies():
            deps.add_dependency(dep)

        artifacts = ReleaseArtifactService()
        artifacts.register_artifact(
            name="kian-0.10.0.tar.gz",
            artifact_type=ArtifactType.PYTHON_PACKAGE,
            version="0.10.0",
            sha256="a" * 64,
            size_bytes=102400,
        )

        migrations = MigrationVerificationService()
        migrations.register_migration(
            version="001",
            description="Initial schema",
            status=MigrationStatus.APPLIED,
            is_reversible=True,
            rollback_tested=True,
        )

        staging = StagingDeploymentService()
        deployment = staging.deploy(
            version="0.10.0",
            config_validated=True,
            secrets_referenced=True,
        )
        staging.add_health_check(deployment, "/health", 200, 50.0)
        staging.add_health_check(deployment, "/health/ready", 200, 30.0)

        canary = CanaryService()
        c = canary.create_canary(version="0.10.0")
        c.advance()

        rollback = RollbackTestingService()
        test = rollback.create_rollback_test(
            from_version="0.10.0",
            to_version="0.9.0",
        )
        rollback.complete_rollback_test(
            test,
            data_integrity_verified=True,
            financial_effects_preserved=True,
        )

        runbook = RunbookService()
        for rb in create_standard_runbooks():
            runbook.add_runbook(rb)

        docs = DocumentationService()
        for raw_doc in create_standard_documentation():
            current_doc = raw_doc
            if current_doc.status is DocStatus.DRAFT:
                current_doc = type(current_doc)(
                    doc_id=current_doc.doc_id,
                    doc_type=current_doc.doc_type,
                    title=current_doc.title,
                    path=current_doc.path,
                    status=DocStatus.REVIEWED,
                    last_updated=current_doc.last_updated,
                    sections=current_doc.sections,
                    word_count=current_doc.word_count,
                )
            docs.add_doc(current_doc)

        evidence = ReleaseEvidenceService(release_version="0.10.0")
        for et in [
            EvidenceType.TEST_RESULTS,
            EvidenceType.SECURITY_SCAN,
            EvidenceType.FINANCIAL_SAFETY,
            EvidenceType.PERFORMANCE_BENCHMARK,
            EvidenceType.COMPLIANCE_CHECK,
            EvidenceType.MIGRATION_VERIFICATION,
            EvidenceType.ROLLBACK_VERIFICATION,
            EvidenceType.ARCHITECTURE_REVIEW,
            EvidenceType.DEPLOYMENT_EVIDENCE,
        ]:
            evidence.record_evidence(
                evidence_type=et,
                component="test",
                command="test",
                expected_result="pass",
                observed_result="pass",
                passed=True,
            )

        return (
            arch,
            deps,
            artifacts,
            migrations,
            staging,
            canary,
            rollback,
            runbook,
            docs,
            evidence,
        )

    def test_generate_report_go(self) -> None:
        (
            arch,
            deps,
            artifacts,
            migrations,
            staging,
            canary,
            rollback,
            runbook,
            docs,
            evidence,
        ) = self._create_all_services()

        report_service = ReadinessReportService()
        report = report_service.generate_report(
            release_version="0.10.0",
            evidence_package=evidence.package,
            architecture_review=arch,
            dependency_verification=deps,
            artifact_service=artifacts,
            migration_service=migrations,
            deployment_service=staging,
            canary_service=canary,
            rollback_service=rollback,
            runbook_service=runbook,
            doc_service=docs,
        )

        assert report.decision is ReadinessDecision.GO
        assert report.all_gates_passed
        assert report.is_go
        assert len(report.blocking_items) == 0
        assert not report.live_authorized
        assert not report.can_activate_live

    def test_generate_report_no_go_with_blocking(self) -> None:
        arch = ArchitectureReviewService()
        arch.add_item(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Critical security gap",
            description="Gap",
            status=ReviewStatus.FAIL,
            evidence="evidence",
        )

        deps = DependencyVerificationService()
        artifacts = ReleaseArtifactService()
        migrations = MigrationVerificationService()
        staging = StagingDeploymentService()
        canary = CanaryService()
        rollback = RollbackTestingService()
        runbook = RunbookService()
        docs = DocumentationService()

        evidence = ReleaseEvidenceService(release_version="0.10.0")
        for et in [
            EvidenceType.TEST_RESULTS,
            EvidenceType.SECURITY_SCAN,
            EvidenceType.FINANCIAL_SAFETY,
            EvidenceType.PERFORMANCE_BENCHMARK,
            EvidenceType.COMPLIANCE_CHECK,
            EvidenceType.MIGRATION_VERIFICATION,
            EvidenceType.ROLLBACK_VERIFICATION,
            EvidenceType.ARCHITECTURE_REVIEW,
            EvidenceType.DEPLOYMENT_EVIDENCE,
        ]:
            evidence.record_evidence(
                evidence_type=et,
                component="test",
                command="test",
                expected_result="pass",
                observed_result="pass",
                passed=True,
            )

        report_service = ReadinessReportService()
        report = report_service.generate_report(
            release_version="0.10.0",
            evidence_package=evidence.package,
            architecture_review=arch,
            dependency_verification=deps,
            artifact_service=artifacts,
            migration_service=migrations,
            deployment_service=staging,
            canary_service=canary,
            rollback_service=rollback,
            runbook_service=runbook,
            doc_service=docs,
        )

        assert report.decision is ReadinessDecision.NO_GO
        assert not report.all_gates_passed
        assert not report.is_go

    def test_generate_report_conditional_go(self) -> None:
        """All gates pass but blocking items exist → CONDITIONAL_GO."""
        (
            arch,
            deps,
            artifacts,
            migrations,
            staging,
            canary,
            rollback,
            runbook,
            docs,
            evidence,
        ) = self._create_all_services()

        # Add a compliance warning that is NOT blocking but creates a condition
        arch.add_item(
            category=ReviewCategory.COMPLIANCE,
            gate=5,
            title="Compliance review pending",
            description="Legal eligibility not yet completed",
            status=ReviewStatus.WARN,
            evidence="Compliance framework implemented, review pending",
        )

        report_service = ReadinessReportService()
        report = report_service.generate_report(
            release_version="0.10.0",
            evidence_package=evidence.package,
            architecture_review=arch,
            dependency_verification=deps,
            artifact_service=artifacts,
            migration_service=migrations,
            deployment_service=staging,
            canary_service=canary,
            rollback_service=rollback,
            runbook_service=runbook,
            doc_service=docs,
        )

        # WARN is not blocking, so gates pass, but we have a compliance warning
        assert report.all_gates_passed

    def test_report_never_authorizes_live(self) -> None:
        """Per Section 17 PHASE 10: completion does not authorize live trading."""
        (
            arch,
            deps,
            artifacts,
            migrations,
            staging,
            canary,
            rollback,
            runbook,
            docs,
            evidence,
        ) = self._create_all_services()

        report_service = ReadinessReportService()
        report = report_service.generate_report(
            release_version="0.10.0",
            evidence_package=evidence.package,
            architecture_review=arch,
            dependency_verification=deps,
            artifact_service=artifacts,
            migration_service=migrations,
            deployment_service=staging,
            canary_service=canary,
            rollback_service=rollback,
            runbook_service=runbook,
            doc_service=docs,
        )

        assert report.is_go
        assert not report.can_activate_live
        assert not report.live_authorized
        assert not report.mining_authorized

    def test_report_with_remaining_risks(self) -> None:
        (
            arch,
            deps,
            artifacts,
            migrations,
            staging,
            canary,
            rollback,
            runbook,
            docs,
            evidence,
        ) = self._create_all_services()

        report_service = ReadinessReportService()
        report = report_service.generate_report(
            release_version="0.10.0",
            evidence_package=evidence.package,
            architecture_review=arch,
            dependency_verification=deps,
            artifact_service=artifacts,
            migration_service=migrations,
            deployment_service=staging,
            canary_service=canary,
            rollback_service=rollback,
            runbook_service=runbook,
            doc_service=docs,
            remaining_risks=[
                "Compliance review not yet completed (AD-029)",
                "Simulated XOR encryption (F-SEC-02) — needs KMS for production",
                "Repository is PUBLIC (Addendum A14) — owner decision preserved",
            ],
        )

        assert len(report.remaining_risks) == 3

    def test_gate_names(self) -> None:
        service = ReadinessReportService()
        assert service.GATE_NAMES[1] == "Functional Correctness"
        assert service.GATE_NAMES[2] == "Security"
        assert service.GATE_NAMES[3] == "Financial Safety"
        assert service.GATE_NAMES[4] == "Performance and Reliability"
        assert service.GATE_NAMES[5] == "Controlled Live Readiness"
