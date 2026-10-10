"""Release engineering and controlled launch contracts for Kian Trading Intelligence.

Per Section 17 PHASE 10 — Release Engineering and Controlled Launch:
1. Final architecture review (AD-033)
2. Dependency verification (AD-024)
3. Release artifact integrity (AD-024)
4. Migration verification (AD-024)
5. Staging deployment (AD-024)
6. Shadow/canary readiness (AD-024)
7. Rollback testing (AD-024)
8. Operational runbooks (AD-017, AD-028)
9. User documentation (AD-030)
10. Administrator documentation (AD-022)
11. Release evidence package (AD-032)
12. Final readiness report (AD-033)

Per AD-033: Architecture consistency, financial correctness, security,
performance, compliance, and release readiness must be reviewed before
production activation.

Per AD-024: Versioned artifacts, pinned dependencies, compatible migrations,
staged releases, health gates, and safe rollback procedures. Rollback must
not blindly reverse external financial effects.

Per Section 17 PHASE 10 Important: Completion of Phase 10 does not
automatically authorize live trading or physical mining operations.

Per Section 15: If legal eligibility is unresolved, live activation
remains disabled.

Per Section 23 GATE 5: Passing simulation gates does not imply guaranteed
profitability or regulatory approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from uuid import UUID, uuid4

# ── Architecture Review ──


class ReviewStatus(StrEnum):
    """Status of an architecture review item."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    NOT_APPLICABLE = "not_applicable"


class ReviewCategory(StrEnum):
    """Categories for the final architecture review (AD-033)."""

    ARCHITECTURE_CONSISTENCY = "architecture_consistency"
    FINANCIAL_CORRECTNESS = "financial_correctness"
    SECURITY = "security"
    PERFORMANCE = "performance"
    COMPLIANCE = "compliance"
    RELEASE_READINESS = "release_readiness"


@dataclass(frozen=True)
class ReviewItemId:
    """Stable identity for a review item."""

    value: UUID

    @classmethod
    def generate(cls) -> ReviewItemId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ReviewItem:
    """A single architecture review finding (deliverable 1, AD-033).

    Each item maps to one of the five final release gates (Section 23):
    - GATE 1: Functional correctness
    - GATE 2: Security
    - GATE 3: Financial safety
    - GATE 4: Performance and reliability
    - GATE 5: Controlled live readiness
    """

    item_id: ReviewItemId
    category: ReviewCategory
    gate: int
    title: str
    description: str
    status: ReviewStatus
    evidence: str
    remediation: str | None = None
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(  # noqa: PLR0913, PLR0917
        cls,
        category: ReviewCategory,
        gate: int,
        title: str,
        description: str,
        status: ReviewStatus,
        evidence: str,
        remediation: str | None = None,
    ) -> ReviewItem:  # noqa: PLR0913, PLR0917
        MIN_GATE = 1
        MAX_GATE = 5
        if gate < MIN_GATE or gate > MAX_GATE:
            raise ValueError(f"Gate must be 1-5 (Section 23 gates). Got {gate}.")
        return cls(
            item_id=ReviewItemId.generate(),
            category=category,
            gate=gate,
            title=title,
            description=description,
            status=status,
            evidence=evidence,
            remediation=remediation,
        )

    @property
    def is_blocking(self) -> bool:
        """A FAIL status blocks release."""
        return self.status is ReviewStatus.FAIL


# ── Dependency Verification ──


class DependencyStatus(StrEnum):
    """Status of a dependency verification check."""

    VERIFIED = "verified"
    OUTDATED = "outdated"
    VULNERABLE = "vulnerable"
    PINNED = "pinned"
    UNPINNED = "unpinned"


@dataclass(frozen=True)
class DependencyId:
    """Stable identity for a dependency record."""

    value: UUID

    @classmethod
    def generate(cls) -> DependencyId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class DependencyRecord:
    """A single dependency verification record (deliverable 2, AD-024).

    Per AD-024: pinned dependencies with compatible migrations.
    """

    dependency_id: DependencyId
    name: str
    version: str
    declared_version: str
    status: DependencyStatus
    is_pinned: bool
    license_type: str
    compatible: bool
    notes: str = ""

    @classmethod
    def create(  # noqa: PLR0913, PLR0917
        cls,
        name: str,
        version: str,
        declared_version: str,
        status: DependencyStatus,
        is_pinned: bool,
        license_type: str,
        compatible: bool,
        notes: str = "",
    ) -> DependencyRecord:  # noqa: PLR0913, PLR0917
        return cls(
            dependency_id=DependencyId.generate(),
            name=name,
            version=version,
            declared_version=declared_version,
            status=status,
            is_pinned=is_pinned,
            license_type=license_type,
            compatible=compatible,
            notes=notes,
        )

    @property
    def is_blocking(self) -> bool:
        """Vulnerable or incompatible dependencies block release."""
        return self.status is DependencyStatus.VULNERABLE or not self.compatible


# ── Release Artifact Integrity ──


class ArtifactType(StrEnum):
    """Type of release artifact (AD-024)."""

    PYTHON_PACKAGE = "python_package"
    FRONTEND_BUNDLE = "frontend_bundle"
    DOCKER_IMAGE = "docker_image"
    MIGRATION_SCRIPT = "migration_script"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"


class IntegrityStatus(StrEnum):
    """Integrity verification status."""

    VERIFIED = "verified"
    MISMATCH = "mismatch"
    MISSING = "missing"
    CORRUPTED = "corrupted"


@dataclass(frozen=True)
class ArtifactId:
    """Stable identity for a release artifact."""

    value: UUID

    @classmethod
    def generate(cls) -> ArtifactId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ReleaseArtifact:
    """A release artifact with integrity verification (deliverable 3, AD-024).

    Per AD-024: versioned artifacts with integrity checks.
    """

    artifact_id: ArtifactId
    name: str
    artifact_type: ArtifactType
    version: str
    sha256: str
    size_bytes: int
    integrity_status: IntegrityStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(  # noqa: PLR0913, PLR0917
        cls,
        name: str,
        artifact_type: ArtifactType,
        version: str,
        sha256: str,
        size_bytes: int,
        integrity_status: IntegrityStatus = IntegrityStatus.VERIFIED,
    ) -> ReleaseArtifact:  # noqa: PLR0913, PLR0917
        SHA256_LENGTH = 64
        if len(sha256) != SHA256_LENGTH:
            raise ValueError(f"SHA-256 must be 64 hex characters. Got {len(sha256)}.")
        if size_bytes < 0:
            raise ValueError(f"Size must be non-negative. Got {size_bytes}.")
        return cls(
            artifact_id=ArtifactId.generate(),
            name=name,
            artifact_type=artifact_type,
            version=version,
            sha256=sha256,
            size_bytes=size_bytes,
            integrity_status=integrity_status,
        )

    @property
    def is_blocking(self) -> bool:
        """Missing, mismatched, or corrupted artifacts block release."""
        return self.integrity_status is not IntegrityStatus.VERIFIED


# ── Migration Verification ──


class MigrationStatus(StrEnum):
    """Status of a database migration (AD-024)."""

    PENDING = "pending"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class MigrationId:
    """Stable identity for a migration record."""

    value: UUID

    @classmethod
    def generate(cls) -> MigrationId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class MigrationRecord:
    """A database migration verification record (deliverable 4, AD-024).

    Per AD-024: compatible migrations with safe rollback procedures.
    Per Section 11.5: versioned migrations, explicit constraints,
    transactional financial posting, and tested recovery procedures.
    """

    migration_id: MigrationId
    version: str
    description: str
    status: MigrationStatus
    is_reversible: bool
    applied_at: datetime | None = None
    rollback_tested: bool = False
    dependency_chain: list[str] = field(default_factory=list)

    @classmethod
    def create(  # noqa: PLR0913, PLR0917
        cls,
        version: str,
        description: str,
        status: MigrationStatus,
        is_reversible: bool,
        rollback_tested: bool = False,
        dependency_chain: list[str] | None = None,
    ) -> MigrationRecord:  # noqa: PLR0913, PLR0917
        return cls(
            migration_id=MigrationId.generate(),
            version=version,
            description=description,
            status=status,
            is_reversible=is_reversible,
            rollback_tested=rollback_tested,
            dependency_chain=dependency_chain if dependency_chain else [],
        )

    @property
    def is_blocking(self) -> bool:
        """Failed or irreversible migrations block release."""
        return self.status is MigrationStatus.FAILED or not self.is_reversible


# ── Staging Deployment ──


class DeploymentStatus(StrEnum):
    """Status of a staging deployment (AD-024)."""

    PENDING = "pending"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass(frozen=True)
class DeploymentId:
    """Stable identity for a deployment record."""

    value: UUID

    @classmethod
    def generate(cls) -> DeploymentId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class HealthCheckResult:
    """Result of a health check on a deployed service."""

    endpoint: str
    status_code: int
    response_time_ms: float
    is_healthy: bool
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        endpoint: str,
        status_code: int,
        response_time_ms: float,
    ) -> HealthCheckResult:
        HTTP_OK = 200
        is_healthy = status_code == HTTP_OK
        return cls(
            endpoint=endpoint,
            status_code=status_code,
            response_time_ms=response_time_ms,
            is_healthy=is_healthy,
        )


@dataclass
class StagingDeployment:
    """A staging deployment record (deliverable 5, AD-024).

    Per AD-024: staged releases with health gates.
    Per AD-017: health gates before trading resumption.
    """

    deployment_id: DeploymentId
    version: str
    environment: str
    status: DeploymentStatus
    health_checks: list[HealthCheckResult] = field(default_factory=list)
    deployed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    config_validated: bool = False
    secrets_referenced: bool = False

    @classmethod
    def create(
        cls,
        version: str,
        environment: str = "staging",
        status: DeploymentStatus = DeploymentStatus.PENDING,
        config_validated: bool = False,
        secrets_referenced: bool = False,
    ) -> StagingDeployment:
        return cls(
            deployment_id=DeploymentId.generate(),
            version=version,
            environment=environment,
            status=status,
            config_validated=config_validated,
            secrets_referenced=secrets_referenced,
        )

    def add_health_check(self, check: HealthCheckResult) -> None:
        """Add a health check result."""
        self.health_checks.append(check)
        all_healthy = all(c.is_healthy for c in self.health_checks)
        MIN_HEALTH_CHECKS = 2
        if all_healthy and len(self.health_checks) >= MIN_HEALTH_CHECKS:
            self.status = DeploymentStatus.HEALTHY
        elif self.health_checks and not all_healthy:
            self.status = DeploymentStatus.UNHEALTHY

    @property
    def all_health_checks_passed(self) -> bool:
        """True if all health checks passed."""
        return len(self.health_checks) > 0 and all(c.is_healthy for c in self.health_checks)

    @property
    def is_blocking(self) -> bool:
        """Unhealthy or failed deployments block release."""
        return self.status in (
            DeploymentStatus.UNHEALTHY,
            DeploymentStatus.FAILED,
        )


# ── Shadow / Canary Readiness ──


class CanaryStatus(StrEnum):
    """Status of a shadow/canary deployment (AD-024)."""

    PENDING = "pending"
    SHADOW = "shadow"
    CANARY_10 = "canary_10"
    CANARY_50 = "canary_50"
    CANARY_100 = "canary_100"
    PROMOTED = "promoted"
    ABORTED = "aborted"


@dataclass(frozen=True)
class CanaryId:
    """Stable identity for a canary deployment."""

    value: UUID

    @classmethod
    def generate(cls) -> CanaryId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class CanaryMetrics:
    """Metrics collected during canary/shadow deployment."""

    error_rate: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_per_sec: float
    sample_count: int

    @classmethod
    def create(
        cls,
        error_rate: float,
        latency_p95_ms: float,
        latency_p99_ms: float,
        throughput_per_sec: float,
        sample_count: int,
    ) -> CanaryMetrics:
        if error_rate < 0 or error_rate > 1:
            raise ValueError(f"Error rate must be 0.0-1.0. Got {error_rate}.")
        return cls(
            error_rate=error_rate,
            latency_p95_ms=latency_p95_ms,
            latency_p99_ms=latency_p99_ms,
            throughput_per_sec=throughput_per_sec,
            sample_count=sample_count,
        )

    @property
    def within_targets(self) -> bool:
        """Check if metrics are within provisional targets (Section 14.2).

        API read p95: 300ms, API write p95: 500ms, risk p99: 100ms.
        """
        MAX_ERROR_RATE = 0.01
        MAX_LATENCY_P95 = 500.0
        MAX_LATENCY_P99 = 100.0
        return (
            self.error_rate < MAX_ERROR_RATE
            and self.latency_p95_ms <= MAX_LATENCY_P95
            and self.latency_p99_ms <= MAX_LATENCY_P99
        )


@dataclass
class CanaryDeployment:
    """A shadow/canary deployment record (deliverable 6, AD-024).

    Per AD-024: staged releases with progressive traffic shifting.
    Shadow mode processes traffic without affecting production state.
    Canary mode shifts a percentage of traffic to the new version.
    """

    canary_id: CanaryId
    version: str
    status: CanaryStatus
    metrics: CanaryMetrics | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    abort_reason: str | None = None

    @classmethod
    def create(
        cls,
        version: str,
        status: CanaryStatus = CanaryStatus.PENDING,
    ) -> CanaryDeployment:
        return cls(
            canary_id=CanaryId.generate(),
            version=version,
            status=status,
        )

    def set_metrics(self, metrics: CanaryMetrics) -> None:
        """Set metrics and evaluate canary health."""
        self.metrics = metrics
        if not metrics.within_targets:
            self.status = CanaryStatus.ABORTED
            self.abort_reason = (
                f"Metrics outside targets: error_rate={metrics.error_rate}, "
                f"p95={metrics.latency_p95_ms}ms, p99={metrics.latency_p99_ms}ms"
            )

    def advance(self) -> CanaryStatus:
        """Advance the canary to the next stage."""
        if self.status is CanaryStatus.ABORTED:
            raise PermissionError("Cannot advance an aborted canary deployment.")
        if self.status is CanaryStatus.PROMOTED:
            raise PermissionError("Cannot advance a promoted canary deployment.")
        progression: dict[CanaryStatus, CanaryStatus] = {
            CanaryStatus.PENDING: CanaryStatus.SHADOW,
            CanaryStatus.SHADOW: CanaryStatus.CANARY_10,
            CanaryStatus.CANARY_10: CanaryStatus.CANARY_50,
            CanaryStatus.CANARY_50: CanaryStatus.CANARY_100,
            CanaryStatus.CANARY_100: CanaryStatus.PROMOTED,
        }
        self.status = progression[self.status]
        return self.status

    @property
    def is_blocking(self) -> bool:
        """Aborted canaries block release."""
        return self.status is CanaryStatus.ABORTED


# ── Rollback Testing ──


class RollbackStatus(StrEnum):
    """Status of a rollback test."""

    PENDING = "pending"
    INITIATED = "initiated"
    COMPLETED = "completed"
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class RollbackId:
    """Stable identity for a rollback test record."""

    value: UUID

    @classmethod
    def generate(cls) -> RollbackId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class RollbackTest:
    """A rollback test record (deliverable 7, AD-024).

    Per AD-024: safe rollback procedures. Rollback must NOT blindly
    reverse external financial effects.

    Per Section 12: Infrastructure recovery does not authorize trading
    recovery. Cloud restart must never silently restore live trading
    after a critical failure.

    Per AD-017: services must recover without creating duplicate
    financial effects.
    """

    rollback_id: RollbackId
    from_version: str
    to_version: str
    status: RollbackStatus
    data_integrity_verified: bool = False
    financial_effects_preserved: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration: timedelta | None = None
    notes: str = ""

    @classmethod
    def create(
        cls,
        from_version: str,
        to_version: str,
        status: RollbackStatus = RollbackStatus.PENDING,
        notes: str = "",
    ) -> RollbackTest:
        return cls(
            rollback_id=RollbackId.generate(),
            from_version=from_version,
            to_version=to_version,
            status=status,
            notes=notes,
        )

    def complete(
        self,
        data_integrity_verified: bool,
        financial_effects_preserved: bool,
    ) -> None:
        """Mark the rollback test as completed.

        Per AD-024: rollback must not blindly reverse external financial
        effects. The `financial_effects_preserved` flag confirms that
        external financial state was not reversed.
        """
        self.data_integrity_verified = data_integrity_verified
        self.financial_effects_preserved = financial_effects_preserved
        if data_integrity_verified and financial_effects_preserved:
            self.status = RollbackStatus.VERIFIED
        else:
            self.status = RollbackStatus.PARTIAL
        self.completed_at = datetime.now(UTC)
        if self.completed_at and self.started_at:
            self.duration = self.completed_at - self.started_at

    @property
    def is_blocking(self) -> bool:
        """Failed or partial rollbacks block release.

        Per AD-024: rollback must not blindly reverse external financial
        effects. A completed rollback that did not preserve financial
        effects is blocking. A pending rollback is not yet blocking.
        """
        if self.status in (RollbackStatus.FAILED, RollbackStatus.PARTIAL):
            return True
        if self.status is RollbackStatus.VERIFIED:
            return not self.financial_effects_preserved
        return False


# ── Operational Runbooks ──


class RunbookCategory(StrEnum):
    """Category for operational runbooks (AD-017, AD-028)."""

    EMERGENCY_STOP = "emergency_stop"
    DISASTER_RECOVERY = "disaster_recovery"
    SPLIT_BRAIN = "split_brain"
    FINANCIAL_RECONCILIATION = "financial_reconciliation"
    SECURITY_INCIDENT = "security_incident"
    DEPLOYMENT = "deployment"
    ROLLBACK = "rollback"
    LIVE_ACTIVATION = "live_activation"


@dataclass(frozen=True)
class RunbookId:
    """Stable identity for an operational runbook."""

    value: UUID

    @classmethod
    def generate(cls) -> RunbookId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class RunbookStep:
    """A single step in an operational runbook."""

    step_number: int
    action: str
    expected_result: str
    requires_human_approval: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.step_number < 1:
            raise ValueError(f"Step number must be >= 1. Got {self.step_number}.")


@dataclass
class OperationalRunbook:
    """An operational runbook (deliverable 8, AD-017, AD-028).

    Per AD-017: critical trading failures require SAFE_HALT,
    reconciliation, and human authorization before resumption.
    Per AD-028: disaster recovery with human-controlled trading recovery.
    Per Section 12: infrastructure recovery does not authorize trading
    recovery.
    """

    runbook_id: RunbookId
    category: RunbookCategory
    title: str
    description: str
    steps: list[RunbookStep]
    last_reviewed: datetime = field(default_factory=lambda: datetime.now(UTC))
    human_approval_required: bool = True

    @classmethod
    def create(
        cls,
        category: RunbookCategory,
        title: str,
        description: str,
        steps: list[RunbookStep],
        human_approval_required: bool = True,
    ) -> OperationalRunbook:
        if not steps:
            raise ValueError("Runbook must have at least one step.")
        for i, step in enumerate(steps):
            if step.step_number != i + 1:
                raise ValueError(
                    f"Steps must be sequentially numbered starting at 1. "
                    f"Step {step.step_number} at index {i} is misnumbered."
                )
        return cls(
            runbook_id=RunbookId.generate(),
            category=category,
            title=title,
            description=description,
            steps=steps,
            human_approval_required=human_approval_required,
        )

    @property
    def has_human_gate(self) -> bool:
        """True if any step requires human approval."""
        return self.human_approval_required or any(s.requires_human_approval for s in self.steps)

    @property
    def is_blocking(self) -> bool:
        """A runbook is never blocking — it is documentation."""
        return False


# ── Documentation ──


class DocType(StrEnum):
    """Type of documentation (AD-030, AD-022)."""

    USER_GUIDE = "user_guide"
    ADMIN_GUIDE = "admin_guide"
    API_REFERENCE = "api_reference"
    ARCHITECTURE_DOC = "architecture_doc"
    RUNBOOK = "runbook"
    RELEASE_NOTES = "release_notes"
    COMPLIANCE_DOC = "compliance_doc"


class DocStatus(StrEnum):
    """Status of documentation."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    OUTDATED = "outdated"
    MISSING = "missing"


@dataclass(frozen=True)
class DocId:
    """Stable identity for a documentation record."""

    value: UUID

    @classmethod
    def generate(cls) -> DocId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class DocumentationRecord:
    """A documentation record (deliverables 9, 10, AD-030, AD-022).

    Per AD-030: unified MacBook and iPhone experience backed by cloud
    authorization — user documentation must cover all surfaces.
    Per AD-022: administrative documentation with audit controls.
    """

    doc_id: DocId
    doc_type: DocType
    title: str
    path: str
    status: DocStatus
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    sections: int = 0
    word_count: int = 0

    @classmethod
    def create(  # noqa: PLR0913, PLR0917
        cls,
        doc_type: DocType,
        title: str,
        path: str,
        status: DocStatus,
        sections: int = 0,
        word_count: int = 0,
    ) -> DocumentationRecord:  # noqa: PLR0913, PLR0917
        if sections < 0:
            raise ValueError(f"Sections must be non-negative. Got {sections}.")
        if word_count < 0:
            raise ValueError(f"Word count must be non-negative. Got {word_count}.")
        return cls(
            doc_id=DocId.generate(),
            doc_type=doc_type,
            title=title,
            path=path,
            status=status,
            sections=sections,
            word_count=word_count,
        )

    @property
    def is_blocking(self) -> bool:
        """Missing or outdated documentation blocks release."""
        return self.status in (
            DocStatus.MISSING,
            DocStatus.OUTDATED,
        )


# ── Release Evidence Package ──


class EvidenceType(StrEnum):
    """Type of release evidence (AD-032)."""

    TEST_RESULTS = "test_results"
    SECURITY_SCAN = "security_scan"
    FINANCIAL_SAFETY = "financial_safety"
    PERFORMANCE_BENCHMARK = "performance_benchmark"
    MIGRATION_VERIFICATION = "migration_verification"
    ROLLBACK_VERIFICATION = "rollback_verification"
    ARCHITECTURE_REVIEW = "architecture_review"
    DEPLOYMENT_EVIDENCE = "deployment_evidence"
    COMPLIANCE_CHECK = "compliance_check"


@dataclass(frozen=True)
class EvidenceId:
    """Stable identity for an evidence record."""

    value: UUID

    @classmethod
    def generate(cls) -> EvidenceId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class EvidenceRecord:
    """A single evidence record in the release evidence package (deliverable 11).

    Per AD-032: implement only authorized phases, verify outcomes, commit
    and push approved changes, produce evidence, and stop for human approval.
    Per Addendum A03: durable, human-auditable evidence library.
    """

    evidence_id: EvidenceId
    evidence_type: EvidenceType
    component: str
    command: str
    expected_result: str
    observed_result: str
    passed: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    reference: str | None = None

    @classmethod
    def create(  # noqa: PLR0913, PLR0917
        cls,
        evidence_type: EvidenceType,
        component: str,
        command: str,
        expected_result: str,
        observed_result: str,
        passed: bool,
        reference: str | None = None,
    ) -> EvidenceRecord:  # noqa: PLR0913, PLR0917
        return cls(
            evidence_id=EvidenceId.generate(),
            evidence_type=evidence_type,
            component=component,
            command=command,
            expected_result=expected_result,
            observed_result=observed_result,
            passed=passed,
            reference=reference,
        )


@dataclass
class ReleaseEvidencePackage:
    """The complete release evidence package (deliverable 11, AD-032).

    Collects all evidence records for the release. A release cannot
    be promoted if any mandatory evidence is missing or failing.
    """

    release_version: str
    evidence: list[EvidenceRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def add_evidence(self, record: EvidenceRecord) -> None:
        """Add an evidence record."""
        with self._lock:
            self.evidence.append(record)

    @property
    def all_passed(self) -> bool:
        """True if all evidence records passed."""
        return len(self.evidence) > 0 and all(e.passed for e in self.evidence)

    @property
    def failed_count(self) -> int:
        """Count of failing evidence records."""
        return sum(1 for e in self.evidence if not e.passed)

    @property
    def total_count(self) -> int:
        """Total evidence records."""
        return len(self.evidence)

    @property
    def coverage(self) -> set[EvidenceType]:
        """Set of evidence types covered."""
        return {e.evidence_type for e in self.evidence}

    @property
    def is_complete(self) -> bool:
        """True if all mandatory evidence types are present and passing.

        Mandatory types per Section 23 gates:
        - TEST_RESULTS (GATE 1)
        - SECURITY_SCAN (GATE 2)
        - FINANCIAL_SAFETY (GATE 3)
        - PERFORMANCE_BENCHMARK (GATE 4)
        - COMPLIANCE_CHECK (GATE 5)
        - MIGRATION_VERIFICATION
        - ROLLBACK_VERIFICATION
        - ARCHITECTURE_REVIEW
        - DEPLOYMENT_EVIDENCE
        """
        mandatory: set[EvidenceType] = {
            EvidenceType.TEST_RESULTS,
            EvidenceType.SECURITY_SCAN,
            EvidenceType.FINANCIAL_SAFETY,
            EvidenceType.PERFORMANCE_BENCHMARK,
            EvidenceType.COMPLIANCE_CHECK,
            EvidenceType.MIGRATION_VERIFICATION,
            EvidenceType.ROLLBACK_VERIFICATION,
            EvidenceType.ARCHITECTURE_REVIEW,
            EvidenceType.DEPLOYMENT_EVIDENCE,
        }
        covered = {e.evidence_type for e in self.evidence if e.passed}
        return mandatory.issubset(covered)


# ── Final Readiness Report ──


class ReadinessDecision(StrEnum):
    """The final readiness decision (AD-033, Section 23)."""

    GO = "go"
    NO_GO = "no_go"
    CONDITIONAL_GO = "conditional_go"


@dataclass(frozen=True)
class ReadinessReportId:
    """Stable identity for a readiness report."""

    value: UUID

    @classmethod
    def generate(cls) -> ReadinessReportId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class GateResult:
    """Result of a single release gate (Section 23)."""

    gate_number: int
    gate_name: str
    passed: bool
    evidence_count: int
    notes: str = ""

    def __post_init__(self) -> None:
        MIN_GATE = 1
        MAX_GATE = 5
        if self.gate_number < MIN_GATE or self.gate_number > MAX_GATE:
            raise ValueError(f"Gate number must be 1-5. Got {self.gate_number}.")


@dataclass
class FinalReadinessReport:
    """The final readiness report (deliverable 12, AD-033).

    Per AD-033: architecture consistency, financial correctness,
    security, performance, compliance, and release readiness must be
    reviewed before production activation.

    Per Section 23: five release gates must all pass.

    Per Section 17 PHASE 10 Important: Completion of Phase 10 does
    not automatically authorize live trading or physical mining.
    """

    report_id: ReadinessReportId
    release_version: str
    decision: ReadinessDecision
    gates: list[GateResult]
    blocking_items: list[str] = field(default_factory=list)
    remaining_risks: list[str] = field(default_factory=list)
    live_authorized: bool = False
    mining_authorized: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        release_version: str,
        decision: ReadinessDecision,
        gates: list[GateResult],
        blocking_items: list[str] | None = None,
        remaining_risks: list[str] | None = None,
    ) -> FinalReadinessReport:
        if not gates:
            raise ValueError("Readiness report must have at least one gate.")
        return cls(
            report_id=ReadinessReportId.generate(),
            release_version=release_version,
            decision=decision,
            gates=gates,
            blocking_items=blocking_items if blocking_items else [],
            remaining_risks=remaining_risks if remaining_risks else [],
        )

    @property
    def all_gates_passed(self) -> bool:
        """True if all five release gates passed (Section 23)."""
        REQUIRED_GATES = 5
        return len(self.gates) >= REQUIRED_GATES and all(g.passed for g in self.gates)

    @property
    def is_go(self) -> bool:
        """True if the decision is GO and all gates passed."""
        return (
            self.decision is ReadinessDecision.GO
            and self.all_gates_passed
            and len(self.blocking_items) == 0
        )

    @property
    def can_activate_live(self) -> bool:
        """True only if GO decision AND explicit live authorization.

        Per Section 17 PHASE 10: completion does not authorize live trading.
        Per Section 15: if legal eligibility is unresolved, live activation
        remains disabled.
        """
        return self.is_go and self.live_authorized
