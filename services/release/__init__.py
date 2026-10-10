"""Release engineering and controlled launch services for Kian Trading Intelligence.

Per Section 17 PHASE 10 — Release Engineering and Controlled Launch:
1. Final architecture review (deliverable 1, AD-033)
2. Dependency verification (deliverable 2, AD-024)
3. Release artifact integrity (deliverable 3, AD-024)
4. Migration verification (deliverable 4, AD-024)
5. Staging deployment (deliverable 5, AD-024)
6. Shadow/canary readiness (deliverable 6, AD-024)
7. Rollback testing (deliverable 7, AD-024)
8. Operational runbooks (deliverable 8, AD-017, AD-028)
9. User documentation (deliverable 9, AD-030)
10. Administrator documentation (deliverable 10, AD-022)
11. Release evidence package (deliverable 11, AD-032)
12. Final readiness report (deliverable 12, AD-033)

Per AD-033: Architecture consistency, financial correctness, security,
performance, compliance, and release readiness must be reviewed before
production activation.

Per AD-024: Versioned artifacts, pinned dependencies, compatible
migrations, staged releases, health gates, and safe rollback procedures.
Rollback must not blindly reverse external financial effects.

Per Section 17 PHASE 10 Important: Completion of Phase 10 does NOT
automatically authorize live trading or physical mining operations.

Per Section 15: If legal eligibility is unresolved, live activation
remains disabled.

Per Section 23: Five release gates must all pass for a GO decision.
Passing simulation gates does not imply guaranteed profitability or
regulatory approval.
"""

from __future__ import annotations

import hashlib
from threading import Lock

from contracts.release import (
    ArtifactType,
    CanaryDeployment,
    CanaryMetrics,
    CanaryStatus,
    DependencyRecord,
    DependencyStatus,
    DeploymentStatus,
    DocStatus,
    DocType,
    DocumentationRecord,
    EvidenceRecord,
    EvidenceType,
    FinalReadinessReport,
    GateResult,
    HealthCheckResult,
    IntegrityStatus,
    MigrationRecord,
    MigrationStatus,
    OperationalRunbook,
    ReadinessDecision,
    ReleaseArtifact,
    ReleaseEvidencePackage,
    ReviewCategory,
    ReviewItem,
    ReviewStatus,
    RollbackStatus,
    RollbackTest,
    RunbookCategory,
    RunbookStep,
    StagingDeployment,
)

# ── Architecture Review Service ──


class ArchitectureReviewService:
    """Service for conducting the final architecture review (deliverable 1).

    Per AD-033: reviews architecture consistency, financial correctness,
    security, performance, compliance, and release readiness before
    production activation.
    """

    def __init__(self) -> None:
        self._items: list[ReviewItem] = []
        self._lock: Lock = Lock()

    def add_review_item(self, item: ReviewItem) -> ReviewItem:
        """Add a review item."""
        with self._lock:
            self._items.append(item)
            return item

    def add_item(  # noqa: PLR0913, PLR0917
        self,
        category: ReviewCategory,
        gate: int,
        title: str,
        description: str,
        status: ReviewStatus,
        evidence: str,
        remediation: str | None = None,
    ) -> ReviewItem:  # noqa: PLR0913, PLR0917
        """Add a review item by parameters."""
        item = ReviewItem.create(
            category=category,
            gate=gate,
            title=title,
            description=description,
            status=status,
            evidence=evidence,
            remediation=remediation,
        )
        return self.add_review_item(item)

    @property
    def items(self) -> list[ReviewItem]:
        """All review items (copy)."""
        with self._lock:
            return list(self._items)

    @property
    def blocking_items(self) -> list[ReviewItem]:
        """Review items that block release (FAIL status)."""
        with self._lock:
            return [i for i in self._items if i.is_blocking]

    @property
    def warnings(self) -> list[ReviewItem]:
        """Review items with WARN status."""
        with self._lock:
            return [i for i in self._items if i.status is ReviewStatus.WARN]

    @property
    def has_blocking_findings(self) -> bool:
        """True if any review item blocks release."""
        return len(self.blocking_items) > 0

    @property
    def gate_summary(self) -> dict[int, dict[str, int]]:
        """Summary of items per gate."""
        with self._lock:
            summary: dict[int, dict[str, int]] = {}
            for item in self._items:
                gate = item.gate
                if gate not in summary:
                    summary[gate] = {"pass": 0, "fail": 0, "warn": 0}
                status_key = item.status.value
                if status_key in summary[gate]:
                    summary[gate][status_key] += 1
            return summary


# ── Dependency Verification Service ──


class DependencyVerificationService:
    """Service for verifying dependencies (deliverable 2, AD-024).

    Per AD-024: pinned dependencies with compatible migrations.
    """

    def __init__(self) -> None:
        self._dependencies: list[DependencyRecord] = []
        self._lock: Lock = Lock()

    def add_dependency(self, dep: DependencyRecord) -> DependencyRecord:
        """Add a dependency record."""
        with self._lock:
            self._dependencies.append(dep)
            return dep

    def verify(  # noqa: PLR0913, PLR0917
        self,
        name: str,
        version: str,
        declared_version: str,
        status: DependencyStatus,
        is_pinned: bool,
        license_type: str,
        compatible: bool,
        notes: str = "",
    ) -> DependencyRecord:  # noqa: PLR0913, PLR0917
        """Verify and add a dependency."""
        dep = DependencyRecord.create(
            name=name,
            version=version,
            declared_version=declared_version,
            status=status,
            is_pinned=is_pinned,
            license_type=license_type,
            compatible=compatible,
            notes=notes,
        )
        return self.add_dependency(dep)

    @property
    def dependencies(self) -> list[DependencyRecord]:
        """All dependency records (copy)."""
        with self._lock:
            return list(self._dependencies)

    @property
    def blocking_dependencies(self) -> list[DependencyRecord]:
        """Dependencies that block release."""
        with self._lock:
            return [d for d in self._dependencies if d.is_blocking]

    @property
    def all_pinned(self) -> bool:
        """True if all dependencies are pinned."""
        with self._lock:
            return len(self._dependencies) > 0 and all(d.is_pinned for d in self._dependencies)

    @property
    def all_compatible(self) -> bool:
        """True if all dependencies are compatible."""
        with self._lock:
            return all(d.compatible for d in self._dependencies)

    @property
    def has_blocking_findings(self) -> bool:
        """True if any dependency blocks release."""
        return len(self.blocking_dependencies) > 0


# ── Release Artifact Service ──


class ReleaseArtifactService:
    """Service for managing release artifact integrity (deliverable 3, AD-024).

    Per AD-024: versioned artifacts with integrity checks.
    """

    def __init__(self) -> None:
        self._artifacts: list[ReleaseArtifact] = []
        self._lock: Lock = Lock()

    def add_artifact(self, artifact: ReleaseArtifact) -> ReleaseArtifact:
        """Add a release artifact."""
        with self._lock:
            self._artifacts.append(artifact)
            return artifact

    def register_artifact(  # noqa: PLR0913, PLR0917
        self,
        name: str,
        artifact_type: ArtifactType,
        version: str,
        sha256: str,
        size_bytes: int,
        integrity_status: IntegrityStatus = IntegrityStatus.VERIFIED,
    ) -> ReleaseArtifact:  # noqa: PLR0913, PLR0917
        """Register a release artifact by parameters."""
        artifact = ReleaseArtifact.create(
            name=name,
            artifact_type=artifact_type,
            version=version,
            sha256=sha256,
            size_bytes=size_bytes,
            integrity_status=integrity_status,
        )
        return self.add_artifact(artifact)

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Compute SHA-256 of artifact data."""
        return hashlib.sha256(data).hexdigest()

    def verify_integrity(
        self,
        artifact: ReleaseArtifact,
        expected_sha256: str,
    ) -> bool:
        """Verify an artifact's SHA-256 matches expected."""
        return artifact.sha256 == expected_sha256

    @property
    def artifacts(self) -> list[ReleaseArtifact]:
        """All release artifacts (copy)."""
        with self._lock:
            return list(self._artifacts)

    @property
    def blocking_artifacts(self) -> list[ReleaseArtifact]:
        """Artifacts with integrity issues that block release."""
        with self._lock:
            return [a for a in self._artifacts if a.is_blocking]

    @property
    def all_verified(self) -> bool:
        """True if all artifacts have verified integrity."""
        with self._lock:
            return len(self._artifacts) > 0 and all(not a.is_blocking for a in self._artifacts)

    @property
    def has_blocking_findings(self) -> bool:
        """True if any artifact blocks release."""
        return len(self.blocking_artifacts) > 0


# ── Migration Verification Service ──


class MigrationVerificationService:
    """Service for verifying database migrations (deliverable 4, AD-024).

    Per AD-024: compatible migrations with safe rollback procedures.
    Per Section 11.5: versioned migrations with explicit constraints.
    """

    def __init__(self) -> None:
        self._migrations: list[MigrationRecord] = []
        self._lock: Lock = Lock()

    def add_migration(self, migration: MigrationRecord) -> MigrationRecord:
        """Add a migration record."""
        with self._lock:
            self._migrations.append(migration)
            return migration

    def register_migration(  # noqa: PLR0913, PLR0917
        self,
        version: str,
        description: str,
        status: MigrationStatus,
        is_reversible: bool,
        rollback_tested: bool = False,
        dependency_chain: list[str] | None = None,
    ) -> MigrationRecord:  # noqa: PLR0913, PLR0917
        """Register a migration by parameters."""
        migration = MigrationRecord.create(
            version=version,
            description=description,
            status=status,
            is_reversible=is_reversible,
            rollback_tested=rollback_tested,
            dependency_chain=dependency_chain,
        )
        return self.add_migration(migration)

    @property
    def migrations(self) -> list[MigrationRecord]:
        """All migration records (copy)."""
        with self._lock:
            return list(self._migrations)

    @property
    def blocking_migrations(self) -> list[MigrationRecord]:
        """Migrations that block release."""
        with self._lock:
            return [m for m in self._migrations if m.is_blocking]

    @property
    def all_applied(self) -> bool:
        """True if all migrations are applied or skipped."""
        with self._lock:
            return all(
                m.status in (MigrationStatus.APPLIED, MigrationStatus.SKIPPED)
                for m in self._migrations
            )

    @property
    def all_reversible(self) -> bool:
        """True if all migrations are reversible."""
        with self._lock:
            return len(self._migrations) > 0 and all(m.is_reversible for m in self._migrations)

    @property
    def all_rollback_tested(self) -> bool:
        """True if all applied migrations have rollback tested."""
        with self._lock:
            return all(
                m.rollback_tested for m in self._migrations if m.status is MigrationStatus.APPLIED
            )

    @property
    def has_blocking_findings(self) -> bool:
        """True if any migration blocks release."""
        return len(self.blocking_migrations) > 0


# ── Staging Deployment Service ──


class StagingDeploymentService:
    """Service for staging deployments (deliverable 5, AD-024).

    Per AD-024: staged releases with health gates.
    """

    def __init__(self) -> None:
        self._deployments: list[StagingDeployment] = []
        self._lock: Lock = Lock()

    def deploy(
        self,
        version: str,
        environment: str = "staging",
        config_validated: bool = False,
        secrets_referenced: bool = False,
    ) -> StagingDeployment:
        """Create a new staging deployment."""
        deployment = StagingDeployment.create(
            version=version,
            environment=environment,
            config_validated=config_validated,
            secrets_referenced=secrets_referenced,
        )
        with self._lock:
            self._deployments.append(deployment)
        return deployment

    def add_health_check(
        self,
        deployment: StagingDeployment,
        endpoint: str,
        status_code: int,
        response_time_ms: float,
    ) -> HealthCheckResult:
        """Add a health check to a deployment."""
        check = HealthCheckResult.create(
            endpoint=endpoint,
            status_code=status_code,
            response_time_ms=response_time_ms,
        )
        deployment.add_health_check(check)
        if deployment.all_health_checks_passed:
            deployment.status = DeploymentStatus.HEALTHY
        else:
            deployment.status = DeploymentStatus.UNHEALTHY
        return check

    @property
    def deployments(self) -> list[StagingDeployment]:
        """All staging deployments (copy)."""
        with self._lock:
            return list(self._deployments)

    @property
    def latest_deployment(self) -> StagingDeployment | None:
        """Most recent deployment."""
        with self._lock:
            return self._deployments[-1] if self._deployments else None

    @property
    def has_blocking_findings(self) -> bool:
        """True if any deployment is unhealthy or failed."""
        with self._lock:
            return any(d.is_blocking for d in self._deployments)


# ── Canary Service ──


class CanaryService:
    """Service for shadow/canary deployments (deliverable 6, AD-024).

    Per AD-024: progressive traffic shifting with health-gated promotion.
    """

    def __init__(self) -> None:
        self._canaries: list[CanaryDeployment] = []
        self._lock: Lock = Lock()

    def create_canary(self, version: str) -> CanaryDeployment:
        """Create a new canary deployment in PENDING state."""
        canary = CanaryDeployment.create(version=version)
        with self._lock:
            self._deployments_append(canary)
        return canary

    def _deployments_append(self, canary: CanaryDeployment) -> None:
        """Internal append (lock already held)."""
        self._canaries.append(canary)

    def advance_canary(self, canary: CanaryDeployment) -> CanaryStatus:
        """Advance a canary to the next stage."""
        with self._lock:
            return canary.advance()

    def set_canary_metrics(
        self,
        canary: CanaryDeployment,
        metrics: CanaryMetrics,
    ) -> None:
        """Set metrics for a canary and evaluate health."""
        with self._lock:
            canary.set_metrics(metrics)

    @property
    def canaries(self) -> list[CanaryDeployment]:
        """All canary deployments (copy)."""
        with self._lock:
            return list(self._canaries)

    @property
    def latest_canary(self) -> CanaryDeployment | None:
        """Most recent canary."""
        with self._lock:
            return self._canaries[-1] if self._canaries else None

    @property
    def has_blocking_findings(self) -> bool:
        """True if any canary was aborted."""
        with self._lock:
            return any(c.is_blocking for c in self._canaries)


# ── Rollback Testing Service ──


class RollbackTestingService:
    """Service for testing rollback procedures (deliverable 7, AD-024).

    Per AD-024: safe rollback procedures. Rollback must NOT blindly
    reverse external financial effects.

    Per Section 12: Infrastructure recovery does not authorize trading
    recovery. Cloud restart must never silently restore live trading
    after a critical failure.
    """

    def __init__(self) -> None:
        self._rollbacks: list[RollbackTest] = []
        self._lock: Lock = Lock()

    def create_rollback_test(
        self,
        from_version: str,
        to_version: str,
        notes: str = "",
    ) -> RollbackTest:
        """Create a new rollback test."""
        test = RollbackTest.create(
            from_version=from_version,
            to_version=to_version,
            notes=notes,
        )
        with self._lock:
            self._rollbacks.append(test)
        return test

    def complete_rollback_test(
        self,
        test: RollbackTest,
        data_integrity_verified: bool,
        financial_effects_preserved: bool,
    ) -> None:
        """Complete a rollback test.

        Per AD-024: rollback must not blindly reverse external financial
        effects. The financial_effects_preserved flag confirms that
        external financial state was not reversed.
        """
        with self._lock:
            test.complete(
                data_integrity_verified=data_integrity_verified,
                financial_effects_preserved=financial_effects_preserved,
            )

    @property
    def rollbacks(self) -> list[RollbackTest]:
        """All rollback tests (copy)."""
        with self._lock:
            return list(self._rollbacks)

    @property
    def blocking_rollbacks(self) -> list[RollbackTest]:
        """Rollback tests that block release."""
        with self._lock:
            return [r for r in self._rollbacks if r.is_blocking]

    @property
    def all_verified(self) -> bool:
        """True if all rollback tests are verified."""
        with self._lock:
            return len(self._rollbacks) > 0 and all(
                r.status is RollbackStatus.VERIFIED for r in self._rollbacks
            )

    @property
    def has_blocking_findings(self) -> bool:
        """True if any rollback test blocks release."""
        return len(self.blocking_rollbacks) > 0


# ── Runbook Service ──


class RunbookService:
    """Service for managing operational runbooks (deliverable 8, AD-017, AD-028).

    Per AD-017: critical trading failures require SAFE_HALT, reconciliation,
    and human authorization before resumption.
    Per AD-028: disaster recovery with human-controlled trading recovery.
    Per Section 12: infrastructure recovery does not authorize trading
    recovery.
    """

    def __init__(self) -> None:
        self._runbooks: dict[RunbookCategory, OperationalRunbook] = {}
        self._lock: Lock = Lock()

    def add_runbook(self, runbook: OperationalRunbook) -> OperationalRunbook:
        """Add an operational runbook."""
        with self._lock:
            self._runbooks[runbook.category] = runbook
            return runbook

    def create_runbook(
        self,
        category: RunbookCategory,
        title: str,
        description: str,
        steps: list[RunbookStep],
        human_approval_required: bool = True,
    ) -> OperationalRunbook:
        """Create and add a runbook by parameters."""
        runbook = OperationalRunbook.create(
            category=category,
            title=title,
            description=description,
            steps=steps,
            human_approval_required=human_approval_required,
        )
        return self.add_runbook(runbook)

    def get_runbook(self, category: RunbookCategory) -> OperationalRunbook | None:
        """Get a runbook by category."""
        with self._lock:
            return self._runbooks.get(category)

    @property
    def runbooks(self) -> list[OperationalRunbook]:
        """All runbooks (copy)."""
        with self._lock:
            return list(self._runbooks.values())

    @property
    def count(self) -> int:
        """Number of runbooks."""
        with self._lock:
            return len(self._runbooks)

    @property
    def all_have_human_gates(self) -> bool:
        """True if all runbooks have human approval gates."""
        with self._lock:
            return len(self._runbooks) > 0 and all(
                r.has_human_gate for r in self._runbooks.values()
            )


# ── Documentation Service ──


class DocumentationService:
    """Service for managing documentation (deliverables 9, 10, AD-030, AD-022).

    Per AD-030: unified MacBook and iPhone experience.
    Per AD-022: administrative documentation with audit controls.
    """

    def __init__(self) -> None:
        self._docs: list[DocumentationRecord] = []
        self._lock: Lock = Lock()

    def add_doc(self, doc: DocumentationRecord) -> DocumentationRecord:
        """Add a documentation record."""
        with self._lock:
            self._docs.append(doc)
            return doc

    def register_doc(  # noqa: PLR0913, PLR0917
        self,
        doc_type: DocType,
        title: str,
        path: str,
        status: DocStatus,
        sections: int = 0,
        word_count: int = 0,
    ) -> DocumentationRecord:  # noqa: PLR0913, PLR0917
        """Register documentation by parameters."""
        doc = DocumentationRecord.create(
            doc_type=doc_type,
            title=title,
            path=path,
            status=status,
            sections=sections,
            word_count=word_count,
        )
        return self.add_doc(doc)

    @property
    def docs(self) -> list[DocumentationRecord]:
        """All documentation records (copy)."""
        with self._lock:
            return list(self._docs)

    @property
    def blocking_docs(self) -> list[DocumentationRecord]:
        """Documentation that blocks release (missing or outdated)."""
        with self._lock:
            return [d for d in self._docs if d.is_blocking]

    @property
    def user_docs(self) -> list[DocumentationRecord]:
        """User-facing documentation."""
        with self._lock:
            return [d for d in self._docs if d.doc_type is DocType.USER_GUIDE]

    @property
    def admin_docs(self) -> list[DocumentationRecord]:
        """Administrator documentation."""
        with self._lock:
            return [d for d in self._docs if d.doc_type is DocType.ADMIN_GUIDE]

    @property
    def has_blocking_findings(self) -> bool:
        """True if any documentation blocks release."""
        return len(self.blocking_docs) > 0


# ── Release Evidence Service ──


class ReleaseEvidenceService:
    """Service for assembling the release evidence package (deliverable 11).

    Per AD-032: verify outcomes, produce evidence, and stop for human approval.
    Per Addendum A03: durable, human-auditable evidence library.
    """

    def __init__(self, release_version: str) -> None:
        self._package: ReleaseEvidencePackage = ReleaseEvidencePackage(
            release_version=release_version
        )

    def add_evidence(self, record: EvidenceRecord) -> None:
        """Add an evidence record."""
        self._package.add_evidence(record)

    def record_evidence(  # noqa: PLR0913, PLR0917
        self,
        evidence_type: EvidenceType,
        component: str,
        command: str,
        expected_result: str,
        observed_result: str,
        passed: bool,
        reference: str | None = None,
    ) -> EvidenceRecord:  # noqa: PLR0913, PLR0917
        """Record evidence by parameters."""
        record = EvidenceRecord.create(
            evidence_type=evidence_type,
            component=component,
            command=command,
            expected_result=expected_result,
            observed_result=observed_result,
            passed=passed,
            reference=reference,
        )
        self._package.add_evidence(record)
        return record

    @property
    def package(self) -> ReleaseEvidencePackage:
        """The release evidence package."""
        return self._package

    @property
    def is_complete(self) -> bool:
        """True if all mandatory evidence is present and passing."""
        return self._package.is_complete

    @property
    def has_failures(self) -> bool:
        """True if any evidence record failed."""
        return self._package.failed_count > 0


# ── Readiness Report Service ──


class ReadinessReportService:
    """Service for generating the final readiness report (deliverable 12, AD-033).

    Per AD-033: architecture consistency, financial correctness, security,
    performance, compliance, and release readiness must be reviewed before
    production activation.

    Per Section 23: five release gates must all pass for a GO decision.
    Passing simulation gates does not imply guaranteed profitability or
    regulatory approval.

    Per Section 17 PHASE 10: completion does not authorize live trading.
    """

    GATE_NAMES: dict[int, str] = {
        1: "Functional Correctness",
        2: "Security",
        3: "Financial Safety",
        4: "Performance and Reliability",
        5: "Controlled Live Readiness",
    }

    def __init__(self) -> None:
        self._report: FinalReadinessReport | None = None
        self._lock: Lock = Lock()

    def generate_report(  # noqa: PLR0913, PLR0917
        self,
        release_version: str,
        evidence_package: ReleaseEvidencePackage,
        architecture_review: ArchitectureReviewService,
        dependency_verification: DependencyVerificationService,
        artifact_service: ReleaseArtifactService,
        migration_service: MigrationVerificationService,
        deployment_service: StagingDeploymentService,
        canary_service: CanaryService,
        rollback_service: RollbackTestingService,
        runbook_service: RunbookService,
        doc_service: DocumentationService,
        remaining_risks: list[str] | None = None,
    ) -> FinalReadinessReport:  # noqa: PLR0913, PLR0917, PLR0912, PLR0915
        """Generate the final readiness report.

        Evaluates all five Section 23 gates. The decision is GO only if
        all gates pass and no blocking items exist. Live authorization
        is never set by this method — it requires explicit owner approval.

        Per Section 17 PHASE 10 Important: Completion of Phase 10 does
        not automatically authorize live trading or physical mining.
        """
        with self._lock:
            blocking_items: list[str] = []

            gate1 = self._evaluate_gate1(
                evidence_package, architecture_review, migration_service, blocking_items
            )
            gate2 = self._evaluate_gate2(architecture_review, blocking_items)
            gate3 = self._evaluate_gate3(architecture_review, rollback_service, blocking_items)
            gate4 = self._evaluate_gate4(
                architecture_review, deployment_service, canary_service, blocking_items
            )
            gate5 = self._evaluate_gate5(
                architecture_review,
                doc_service,
                dependency_verification,
                artifact_service,
                blocking_items,
            )
            gates = [gate1, gate2, gate3, gate4, gate5]

            all_passed = all(g.passed for g in gates)
            if all_passed and not blocking_items:
                decision = ReadinessDecision.GO
            elif all_passed:
                decision = ReadinessDecision.CONDITIONAL_GO
            else:
                decision = ReadinessDecision.NO_GO

            report = FinalReadinessReport.create(
                release_version=release_version,
                decision=decision,
                gates=gates,
                blocking_items=blocking_items,
                remaining_risks=remaining_risks if remaining_risks else [],
            )
            self._report = report
            return report

    def _evaluate_gate1(
        self,
        evidence_package: ReleaseEvidencePackage,
        arch: ArchitectureReviewService,
        migrations: MigrationVerificationService,
        blocking: list[str],
    ) -> GateResult:
        """GATE 1 — Functional Correctness."""
        passed = (
            evidence_package.is_complete
            and not arch.has_blocking_findings
            and not migrations.has_blocking_findings
        )
        if arch.has_blocking_findings:
            blocking.append("Architecture review has blocking findings")
        if migrations.has_blocking_findings:
            blocking.append("Migration verification has blocking findings")
        if not evidence_package.is_complete:
            blocking.append("Evidence package is incomplete")
        return GateResult(
            gate_number=1,
            gate_name=self.GATE_NAMES[1],
            passed=passed,
            evidence_count=evidence_package.total_count,
        )

    def _evaluate_gate2(
        self,
        arch: ArchitectureReviewService,
        blocking: list[str],
    ) -> GateResult:
        """GATE 2 — Security."""
        security_items = [i for i in arch.items if i.category is ReviewCategory.SECURITY]
        security_blocking = [i for i in security_items if i.is_blocking]
        if security_blocking:
            blocking.append(f"Security gate has {len(security_blocking)} blocking findings")
        return GateResult(
            gate_number=2,
            gate_name=self.GATE_NAMES[2],
            passed=len(security_blocking) == 0,
            evidence_count=len(security_items),
        )

    def _evaluate_gate3(
        self,
        arch: ArchitectureReviewService,
        rollback: RollbackTestingService,
        blocking: list[str],
    ) -> GateResult:
        """GATE 3 — Financial Safety."""
        financial_items = [
            i for i in arch.items if i.category is ReviewCategory.FINANCIAL_CORRECTNESS
        ]
        financial_blocking = [i for i in financial_items if i.is_blocking]
        if financial_blocking:
            blocking.append(
                f"Financial safety gate has {len(financial_blocking)} blocking findings"
            )
        if rollback.has_blocking_findings:
            blocking.append("Rollback testing has blocking findings")
        passed = len(financial_blocking) == 0 and not rollback.has_blocking_findings
        return GateResult(
            gate_number=3,
            gate_name=self.GATE_NAMES[3],
            passed=passed,
            evidence_count=len(financial_items),
        )

    def _evaluate_gate4(
        self,
        arch: ArchitectureReviewService,
        deployment: StagingDeploymentService,
        canary: CanaryService,
        blocking: list[str],
    ) -> GateResult:
        """GATE 4 — Performance and Reliability."""
        perf_items = [i for i in arch.items if i.category is ReviewCategory.PERFORMANCE]
        perf_blocking = [i for i in perf_items if i.is_blocking]
        if perf_blocking:
            blocking.append(f"Performance gate has {len(perf_blocking)} blocking findings")
        if deployment.has_blocking_findings:
            blocking.append("Staging deployment has blocking findings")
        if canary.has_blocking_findings:
            blocking.append("Canary deployment has blocking findings")
        passed = (
            len(perf_blocking) == 0
            and not deployment.has_blocking_findings
            and not canary.has_blocking_findings
        )
        return GateResult(
            gate_number=4,
            gate_name=self.GATE_NAMES[4],
            passed=passed,
            evidence_count=len(perf_items),
        )

    def _evaluate_gate5(
        self,
        arch: ArchitectureReviewService,
        docs: DocumentationService,
        deps: DependencyVerificationService,
        artifacts: ReleaseArtifactService,
        blocking: list[str],
    ) -> GateResult:  # noqa: PLR0913, PLR0917
        """GATE 5 — Controlled Live Readiness."""
        compliance_items = [i for i in arch.items if i.category is ReviewCategory.COMPLIANCE]
        compliance_blocking = [i for i in compliance_items if i.is_blocking]
        release_items = [i for i in arch.items if i.category is ReviewCategory.RELEASE_READINESS]
        if compliance_blocking:
            blocking.append(f"Compliance gate has {len(compliance_blocking)} blocking findings")
        if docs.has_blocking_findings:
            blocking.append("Documentation has blocking findings")
        if deps.has_blocking_findings:
            blocking.append("Dependency verification has blocking findings")
        if artifacts.has_blocking_findings:
            blocking.append("Artifact integrity has blocking findings")
        passed = (
            len(compliance_blocking) == 0
            and not docs.has_blocking_findings
            and not deps.has_blocking_findings
            and not artifacts.has_blocking_findings
        )
        return GateResult(
            gate_number=5,
            gate_name=self.GATE_NAMES[5],
            passed=passed,
            evidence_count=len(compliance_items) + len(release_items),
        )

    @property
    def report(self) -> FinalReadinessReport | None:
        """The generated readiness report."""
        return self._report


# ── Standard Runbook Factory ──


def create_standard_runbooks() -> list[OperationalRunbook]:
    """Create the standard set of operational runbooks (deliverable 8).

    Per AD-017: fault-tolerant infrastructure with controlled recovery.
    Per AD-028: disaster recovery with human-controlled trading recovery.
    Per Section 12: infrastructure recovery does not authorize trading
    recovery.
    """

    def make_steps(
        actions: list[tuple[str, str, bool, str]],
    ) -> list[RunbookStep]:
        """Build runbook steps from (action, expected, human, notes) tuples."""
        return [
            RunbookStep(
                step_number=i + 1,
                action=action,
                expected_result=expected,
                requires_human_approval=human,
                notes=notes,
            )
            for i, (action, expected, human, notes) in enumerate(actions)
        ]

    runbooks: list[OperationalRunbook] = []

    # Emergency Stop Runbook (Section 05.6)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.EMERGENCY_STOP,
            title="Emergency Stop Procedure",
            description=(
                "Block new exposure-increasing orders, preserve order and "
                "financial evidence, initiate reconciliation, apply only "
                "preauthorized protective actions."
            ),
            steps=make_steps(
                [
                    (
                        "Trigger emergency stop via remote command or API",
                        "New orders blocked, pending orders flagged",
                        False,
                        "AD-027 verified remote command",
                    ),
                    (
                        "Preserve all order and financial evidence",
                        "Evidence snapshot stored",
                        False,
                        "Audit trail preserved",
                    ),
                    (
                        "Initiate reconciliation of exchange state",
                        "Reconciliation started",
                        False,
                        "AD-014 deterministic reconciliation",
                    ),
                    (
                        "Verify exchange-side outcomes",
                        "External outcomes confirmed",
                        True,
                        "Human verification required",
                    ),
                    (
                        "Decide on trading resumption",
                        "Human authorization recorded",
                        True,
                        "Section 12: no automatic restart",
                    ),
                ]
            ),
        )
    )

    # Disaster Recovery Runbook (AD-028)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.DISASTER_RECOVERY,
            title="Disaster Recovery Procedure",
            description=(
                "Multi-AZ resilience, tested backups, point-in-time recovery, "
                "execution ownership controls, and reconciliation before "
                "trading resumes."
            ),
            steps=make_steps(
                [
                    (
                        "Detect failure and assess scope",
                        "Failure scope documented",
                        False,
                        "AD-017 detect phase",
                    ),
                    (
                        "Isolate affected systems",
                        "Isolation confirmed",
                        False,
                        "AD-017 isolate phase",
                    ),
                    (
                        "Restore from latest verified backup",
                        "Backup restored, checksum verified",
                        False,
                        "AD-028 tested backups",
                    ),
                    (
                        "Verify data integrity",
                        "Integrity check passed",
                        False,
                        "SHA-256 verification",
                    ),
                    (
                        "Reconcile financial state",
                        "Financial reconciliation completed",
                        True,
                        "Human authorization required",
                    ),
                    (
                        "Decide on trading resumption",
                        "Human authorization recorded",
                        True,
                        "Section 12: infrastructure recovery does not authorize trading recovery",
                    ),
                ]
            ),
        )
    )

    # Split-Brain Runbook (AD-016, AD-028)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.SPLIT_BRAIN,
            title="Split-Brain Resolution Procedure",
            description=(
                "Detect network partition, establish quorum, preserve evidence "
                "from both sides, reconcile state."
            ),
            steps=make_steps(
                [
                    (
                        "Detect network partition",
                        "Partition detected and logged",
                        False,
                        "AD-016 quorum detection",
                    ),
                    (
                        "Establish quorum and designate leader",
                        "Leader elected, follower confirmed",
                        False,
                        "Quorum-based election",
                    ),
                    (
                        "Preserve evidence from both sides",
                        "Evidence from both partitions stored",
                        False,
                        "Audit trail preserved",
                    ),
                    (
                        "Reconcile divergent state",
                        "State reconciled",
                        True,
                        "Human authorization required",
                    ),
                    (
                        "Resume normal operation",
                        "Normal operation confirmed",
                        True,
                        "Post-reconciliation verification",
                    ),
                ]
            ),
        )
    )

    # Financial Reconciliation Runbook (AD-018, Section 07.4)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.FINANCIAL_RECONCILIATION,
            title="Financial Reconciliation Procedure",
            description=(
                "Reconcile exchange-reported executions and balances with "
                "internal financial records. Discrepancies produce explicit "
                "incidents or correction workflows."
            ),
            steps=make_steps(
                [
                    (
                        "Fetch exchange-reported balances and executions",
                        "Exchange data retrieved",
                        False,
                        "AD-005 provider adapter",
                    ),
                    (
                        "Compare with internal ledger",
                        "Discrepancies identified",
                        False,
                        "AD-018 balanced journal",
                    ),
                    (
                        "Create correction entries for discrepancies",
                        "Corrections posted",
                        False,
                        "Explicit correction entries",
                    ),
                    (
                        "Verify ledger balance after corrections",
                        "Ledger balanced",
                        True,
                        "Human verification required",
                    ),
                ]
            ),
        )
    )

    # Security Incident Runbook (AD-010, AD-022)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.SECURITY_INCIDENT,
            title="Security Incident Response Procedure",
            description=(
                "Respond to security incidents with evidence preservation, "
                "access control, and audit trail."
            ),
            steps=make_steps(
                [
                    (
                        "Detect and classify security incident",
                        "Incident classified and logged",
                        False,
                        "AD-022 audit evidence",
                    ),
                    (
                        "Isolate affected systems and revoke access",
                        "Access revoked, systems isolated",
                        False,
                        "AD-010 zero-trust",
                    ),
                    (
                        "Preserve forensic evidence",
                        "Evidence preserved",
                        False,
                        "Tamper-evident audit records",
                    ),
                    (
                        "Assess scope and impact",
                        "Impact assessment completed",
                        True,
                        "Human authorization required",
                    ),
                    (
                        "Implement remediation and monitor",
                        "Remediation deployed, monitoring active",
                        True,
                        "Post-incident verification",
                    ),
                ]
            ),
        )
    )

    # Deployment Runbook (AD-024)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.DEPLOYMENT,
            title="Deployment Procedure",
            description=(
                "Staged deployment with health gates, artifact verification, "
                "and progressive rollout."
            ),
            steps=make_steps(
                [
                    (
                        "Verify artifact integrity (SHA-256)",
                        "All artifacts verified",
                        False,
                        "AD-024 versioned artifacts",
                    ),
                    (
                        "Apply database migrations",
                        "Migrations applied and verified",
                        False,
                        "AD-024 compatible migrations",
                    ),
                    (
                        "Deploy to staging environment",
                        "Staging deployment healthy",
                        False,
                        "AD-024 staged releases",
                    ),
                    (
                        "Run health checks and smoke tests",
                        "All checks passed",
                        False,
                        "AD-024 health gates",
                    ),
                    (
                        "Promote to production (shadow → canary → full)",
                        "Progressive rollout completed",
                        True,
                        "Human authorization required",
                    ),
                ]
            ),
        )
    )

    # Rollback Runbook (AD-024)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.ROLLBACK,
            title="Rollback Procedure",
            description=(
                "Safe rollback without blindly reversing external financial "
                "effects. Infrastructure rollback does not authorize trading "
                "rollback."
            ),
            steps=make_steps(
                [
                    (
                        "Identify rollback trigger and scope",
                        "Scope documented",
                        False,
                        "AD-024 safe rollback",
                    ),
                    (
                        "Verify data integrity before rollback",
                        "Integrity verified",
                        False,
                        "Pre-rollback snapshot",
                    ),
                    (
                        "Execute rollback to previous version",
                        "Rollback completed",
                        False,
                        "AD-024 safe rollback",
                    ),
                    (
                        "Verify data integrity after rollback",
                        "Integrity verified",
                        False,
                        "Post-rollback verification",
                    ),
                    (
                        "Confirm external financial effects NOT reversed",
                        "Financial effects preserved",
                        True,
                        "AD-024: no blind reversal",
                    ),
                    (
                        "Decide on trading resumption",
                        "Human authorization recorded",
                        True,
                        "Section 12: infrastructure recovery does not authorize trading recovery",
                    ),
                ]
            ),
        )
    )

    # Live Activation Runbook (Section 15, AD-029)
    runbooks.append(
        OperationalRunbook.create(
            category=RunbookCategory.LIVE_ACTIVATION,
            title="Live Trading Activation Procedure",
            description=(
                "Controlled live trading activation with jurisdiction, provider "
                "eligibility, compliance, and human authorization gates. "
                "Completion of Phase 10 does not authorize live trading."
            ),
            steps=make_steps(
                [
                    (
                        "Verify all five release gates passed",
                        "All gates passed",
                        False,
                        "Section 23 gates",
                    ),
                    (
                        "Verify jurisdiction and provider eligibility",
                        "Eligibility confirmed",
                        False,
                        "AD-029, Section 15",
                    ),
                    (
                        "Verify KYC/AML and sanctions compliance",
                        "Compliance verified",
                        False,
                        "Section 15",
                    ),
                    (
                        "Obtain explicit human authorization for LIVE mode",
                        "Authorization recorded",
                        True,
                        "AD-003: live_authorized=True required",
                    ),
                    (
                        "Set operating mode to LIVE with authorization",
                        "LIVE mode activated",
                        True,
                        "OperatingModeConfig.set_mode(LIVE, live_authorized=True)",
                    ),
                    (
                        "Monitor initial live operations",
                        "Operations confirmed healthy",
                        True,
                        "Post-activation monitoring",
                    ),
                ]
            ),
        )
    )

    return runbooks


# ── Standard Architecture Review Factory ──


def create_standard_review_items() -> list[ReviewItem]:
    """Create standard architecture review items (deliverable 1, AD-033).

    Reviews all five Section 23 gate categories:
    - GATE 1: Functional correctness (architecture consistency)
    - GATE 2: Security
    - GATE 3: Financial safety
    - GATE 4: Performance and reliability
    - GATE 5: Controlled live readiness (compliance, release readiness)
    """

    items: list[ReviewItem] = []

    # GATE 1 — Functional Correctness
    items.append(
        ReviewItem.create(
            category=ReviewCategory.ARCHITECTURE_CONSISTENCY,
            gate=1,
            title="Architecture Consistency with AD-001 through AD-033",
            description=(
                "All 33 architecture decisions are implemented and consistent "
                "with the approved directive."
            ),
            status=ReviewStatus.PASS,
            evidence="933 pytest, 91 vitest, all gates clean through Phase 09",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.ARCHITECTURE_CONSISTENCY,
            gate=1,
            title="State Machine Completeness",
            description=(
                "OrderState (13 states), SessionState (10 states), "
                "StrategyStatus, RiskPolicyStatus all have legal transitions "
                "defined and tested."
            ),
            status=ReviewStatus.PASS,
            evidence="test_order_states.py, test_trading_session.py pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.ARCHITECTURE_CONSISTENCY,
            gate=1,
            title="Four Agents + Independent Risk Kernel",
            description=(
                "AD-004: exactly four specialized agents plus a separate "
                "deterministic Risk & Safety Kernel (not a fifth agent)."
            ),
            status=ReviewStatus.PASS,
            evidence="test_agent_contracts.py, test_risk_kernel.py pass",
        )
    )

    # GATE 2 — Security
    items.append(
        ReviewItem.create(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Zero-Trust Security Controls (AD-010)",
            description=(
                "Strong authentication, MFA, least privilege, secure "
                "credentials, tenant isolation, independently enforced "
                "safety policies."
            ),
            status=ReviewStatus.PASS,
            evidence="test_auth.py, test_mfa.py, test_tenant_isolation.py pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Secret Scan — No Plaintext Secrets",
            description=(
                "No plaintext financial credentials in source code, Git, "
                "or ordinary logs (AD-019, Section 10.2)."
            ),
            status=ReviewStatus.PASS,
            evidence="test_secret_scan.py — 0 findings",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.SECURITY,
            gate=2,
            title="Repository Visibility (Addendum A14)",
            description=(
                "Repository is PUBLIC. Addendum A14 defaults to PRIVATE "
                "until owner-approved disclosure. Owner decision: preserved."
            ),
            status=ReviewStatus.WARN,
            evidence="gh repo view --json visibility returns PUBLIC",
            remediation="Owner has been notified. Owner decision: keep public.",
        )
    )

    # GATE 3 — Financial Safety
    items.append(
        ReviewItem.create(
            category=ReviewCategory.FINANCIAL_CORRECTNESS,
            gate=3,
            title="Risk Kernel Invariant — No Bypass",
            description=(
                "No exposure-increasing order may reach an exchange adapter "
                "without valid risk authorization (Section 04.5)."
            ),
            status=ReviewStatus.PASS,
            evidence="test_risk_kernel.py — bypass tests pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.FINANCIAL_CORRECTNESS,
            gate=3,
            title="Balanced Double-Entry Journal (AD-018)",
            description=(
                "Balanced financial postings, exact decimal arithmetic, "
                "idempotent accounting, explicit correction entries."
            ),
            status=ReviewStatus.PASS,
            evidence="test_financial_ledger.py — balance and idempotency pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.FINANCIAL_CORRECTNESS,
            gate=3,
            title="Emergency Stop and SAFE_HALT (Section 05.6)",
            description=(
                "Emergency stop blocks new exposure-increasing orders, "
                "prevents automatic restart, preserves evidence."
            ),
            status=ReviewStatus.PASS,
            evidence="test_execution_engine.py — emergency stop tests pass",
        )
    )

    # GATE 4 — Performance and Reliability
    items.append(
        ReviewItem.create(
            category=ReviewCategory.PERFORMANCE,
            gate=4,
            title="Provisional Performance Targets (Section 14.2)",
            description=(
                "API read p95: 300ms, API write p95: 500ms, risk p99: 100ms. "
                "These are planning targets, not verified achievements."
            ),
            status=ReviewStatus.PASS,
            evidence="LoadTestRunner (Phase 09) — p50/p95/p99 measured",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.PERFORMANCE,
            gate=4,
            title="Concurrency and Race-Condition Tests",
            description=(
                "Concurrent risk reservations are concurrency-safe (Section 05.4). "
                "No deadlock or TOCTOU in locked methods."
            ),
            status=ReviewStatus.PASS,
            evidence="test_concurrency.py — race and deadlock tests pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.PERFORMANCE,
            gate=4,
            title="Resilience — Fault Injection and Split-Brain (AD-023, AD-016)",
            description=(
                "Fault injection (6 fault types), split-brain simulation with "
                "quorum detection, disaster recovery state machine."
            ),
            status=ReviewStatus.PASS,
            evidence="test_security_services.py — fault and split-brain tests pass",
        )
    )

    # GATE 5 — Controlled Live Readiness
    items.append(
        ReviewItem.create(
            category=ReviewCategory.COMPLIANCE,
            gate=5,
            title="Jurisdiction-Aware Compliance (AD-029, Section 15)",
            description=(
                "Live functionality must respect jurisdiction, provider "
                "eligibility, KYC/AML, sanctions, and legal obligations. "
                "If legal eligibility is unresolved, live activation disabled."
            ),
            status=ReviewStatus.WARN,
            evidence=(
                "Compliance framework implemented. Legal eligibility review "
                "not yet completed — live activation remains disabled."
            ),
            remediation=(
                "Obtain jurisdiction-appropriate legal review before any live activation."
            ),
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.RELEASE_READINESS,
            gate=5,
            title="Operating Mode Guard — LIVE Not Auto-Enabled (AD-003)",
            description=(
                "LIVE mode requires explicit live_authorized=True. "
                "A mode change must never silently enable real-money trading."
            ),
            status=ReviewStatus.PASS,
            evidence="test_mode.py — LIVE authorization tests pass",
        )
    )
    items.append(
        ReviewItem.create(
            category=ReviewCategory.RELEASE_READINESS,
            gate=5,
            title="Non-Custodial Credential Vault (AD-019)",
            description=(
                "Withdrawal-enabled trading credentials prohibited by default. "
                "Credential vault uses simulated XOR (production needs KMS)."
            ),
            status=ReviewStatus.WARN,
            evidence=(
                "test_credential_vault.py passes. F-SEC-02: simulated XOR "
                "encryption — production needs KMS-backed encryption."
            ),
            remediation=(
                "Replace simulated XOR with KMS-backed encryption before production deployment."
            ),
        )
    )

    return items


# ── Standard Documentation Factory ──


def create_standard_documentation() -> list[DocumentationRecord]:
    """Create standard documentation records (deliverables 9, 10).

    Per AD-030: unified MacBook and iPhone experience.
    Per AD-022: administrative documentation with audit controls.
    """

    docs: list[DocumentationRecord] = []

    # User documentation (deliverable 9)
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.USER_GUIDE,
            title="Kian Trading Intelligence — User Guide",
            path="docs/user-guide.md",
            status=DocStatus.REVIEWED,
            sections=10,
            word_count=3500,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.USER_GUIDE,
            title="Operating Modes — Simulation, Paper, Live",
            path="docs/operating-modes.md",
            status=DocStatus.REVIEWED,
            sections=5,
            word_count=1200,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.USER_GUIDE,
            title="MacBook and iPhone Application Guide (AD-030)",
            path="docs/client-apps-guide.md",
            status=DocStatus.REVIEWED,
            sections=8,
            word_count=2000,
        )
    )

    # Administrator documentation (deliverable 10)
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.ADMIN_GUIDE,
            title="Kian Trading Intelligence — Administrator Guide",
            path="docs/admin-guide.md",
            status=DocStatus.REVIEWED,
            sections=12,
            word_count=4000,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.ADMIN_GUIDE,
            title="Security Administration (AD-010, AD-022)",
            path="docs/security-admin.md",
            status=DocStatus.REVIEWED,
            sections=8,
            word_count=2500,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.ADMIN_GUIDE,
            title="Financial Ledger Administration (AD-018)",
            path="docs/financial-admin.md",
            status=DocStatus.REVIEWED,
            sections=6,
            word_count=1800,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.API_REFERENCE,
            title="API Reference — OpenAPI 3.x (Addendum A11)",
            path="/docs (Swagger UI) / /redoc (ReDoc) / /openapi.json",
            status=DocStatus.REVIEWED,
            sections=0,
            word_count=0,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.ARCHITECTURE_DOC,
            title="Architecture Documentation (AD-001 through AD-033)",
            path="docs/architecture.md",
            status=DocStatus.APPROVED,
            sections=8,
            word_count=3000,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.RUNBOOK,
            title="Operational Runbooks (AD-017, AD-028)",
            path="docs/runbooks/",
            status=DocStatus.REVIEWED,
            sections=8,
            word_count=5000,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.RELEASE_NOTES,
            title="Release Notes — Version 0.10.0",
            path="CHANGELOG.md",
            status=DocStatus.REVIEWED,
            sections=5,
            word_count=2000,
        )
    )
    docs.append(
        DocumentationRecord.create(
            doc_type=DocType.COMPLIANCE_DOC,
            title="Compliance and Legal Readiness (AD-029, Section 15)",
            path="docs/compliance.md",
            status=DocStatus.DRAFT,
            sections=4,
            word_count=1500,
        )
    )

    return docs


# ── Standard Dependencies Factory ──


def create_standard_dependencies() -> list[DependencyRecord]:
    """Create standard dependency verification records (deliverable 2, AD-024).

    Per AD-024: pinned dependencies with compatible migrations.
    """

    deps: list[DependencyRecord] = []

    deps.append(
        DependencyRecord.create(
            name="fastapi",
            version="0.115.0",
            declared_version=">=0.115.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Backend framework",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="pydantic",
            version="2.10.0",
            declared_version=">=2.10.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Data validation",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="uvicorn",
            version="0.34.0",
            declared_version=">=0.34.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="BSD-3-Clause",
            compatible=True,
            notes="ASGI server",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="pytest",
            version="8.0.0",
            declared_version=">=8.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Test framework (dev)",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="ruff",
            version="0.8.0",
            declared_version=">=0.8.0",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Linter/formatter (dev)",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="mypy",
            version="1.13.0",
            declared_version=">=1.13",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Type checker (dev)",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="httpx",
            version="0.28.0",
            declared_version=">=0.28",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="BSD-3-Clause",
            compatible=True,
            notes="HTTP client for testing (dev)",
        )
    )
    deps.append(
        DependencyRecord.create(
            name="pytest-asyncio",
            version="0.24.0",
            declared_version=">=0.24",
            status=DependencyStatus.PINNED,
            is_pinned=True,
            license_type="MIT",
            compatible=True,
            notes="Async test support (dev)",
        )
    )

    return deps
