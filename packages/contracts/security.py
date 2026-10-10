"""Security, resilience, and scale contracts for Kian Trading Intelligence.

Per Section 17 PHASE 09 — Security, Resilience, and Scale:
- Threat-model review (AD-010, AD-022)
- Security scanning (AD-010)
- Tenant-isolation testing (AD-002, AD-010)
- Risk stress tests (AD-013)
- Financial stress tests (AD-018)
- Backup restoration (AD-028)
- Disaster recovery (AD-017, AD-028)
- Split-brain simulation (AD-016, AD-028)
- Fault injection (AD-023)
- Load testing (AD-016)
- Observability verification (AD-022)
- Cost and token evaluation (AD-025)

Per AD-022: structured logs, distributed traces, operational metrics,
tamper-evident audit records, incident evidence, and measurable service
reliability objectives.

Per AD-028: multi-AZ resilience, tested backups, point-in-time recovery,
execution ownership controls, and reconciliation before trading resumes.

Per AD-017: services must recover without creating duplicate financial
effects. Critical trading failures require SAFE_HALT, reconciliation,
and human authorization before resumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from uuid import UUID, uuid4

# ── Threat Model ──


class ThreatSeverity(StrEnum):
    """Severity levels for threat-model findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ThreatStatus(StrEnum):
    """Status of a threat-model finding."""

    OPEN = "open"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    ACCEPTED_RISK = "accepted_risk"


@dataclass(frozen=True)
class ThreatFindingId:
    """Stable identity for a threat-model finding."""

    value: UUID

    @classmethod
    def generate(cls) -> ThreatFindingId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ThreatFinding:
    """A single threat-model finding (deliverable 1).

    Per AD-010: zero-trust security review component.
    Per AD-022: structured security audit evidence.

    Attributes:
        finding_id: Stable unique identifier.
        component: System component under review.
        threat_vector: Description of the attack vector.
        severity: Severity level.
        status: Resolution status.
        mitigation: Applied or planned mitigation.
        created_at: UTC creation timestamp.
        resolved_at: UTC resolution timestamp (None if unresolved).
    """

    finding_id: ThreatFindingId
    component: str
    threat_vector: str
    severity: ThreatSeverity
    status: ThreatStatus = ThreatStatus.OPEN
    mitigation: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.component:
            raise ValueError("component must not be empty.")
        if not self.threat_vector:
            raise ValueError("threat_vector must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if self.resolved_at is not None and self.resolved_at.tzinfo is None:
            raise ValueError("resolved_at must be timezone-aware (UTC).")
        if self.status is ThreatStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved_at must be set when status is RESOLVED.")

    def resolve(self, mitigation: str = "") -> ThreatFinding:
        """Mark the finding as resolved."""
        return ThreatFinding(
            finding_id=self.finding_id,
            component=self.component,
            threat_vector=self.threat_vector,
            severity=self.severity,
            status=ThreatStatus.RESOLVED,
            mitigation=mitigation or self.mitigation,
            created_at=self.created_at,
            resolved_at=datetime.now(UTC),
        )

    def mitigate(self, mitigation: str) -> ThreatFinding:
        """Mark the finding as mitigated."""
        return ThreatFinding(
            finding_id=self.finding_id,
            component=self.component,
            threat_vector=self.threat_vector,
            severity=self.severity,
            status=ThreatStatus.MITIGATED,
            mitigation=mitigation,
            created_at=self.created_at,
            resolved_at=self.resolved_at,
        )


@dataclass
class ThreatModelReport:
    """Threat-model review report (deliverable 1).

    Per AD-010: zero-trust security review.
    Per AD-022: security audit evidence.

    Attributes:
        report_id: Stable unique identifier.
        scope: Scope of the review (components covered).
        findings: All findings discovered during the review.
        created_at: UTC creation timestamp.
        critical_findings: Count of critical findings.
        high_findings: Count of high-severity findings.
        resolved_count: Count of resolved findings.
    """

    report_id: UUID
    scope: str
    findings: list[ThreatFinding] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.scope:
            raise ValueError("scope must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    @property
    def critical_findings(self) -> int:
        """Count of critical findings."""
        return sum(1 for f in self.findings if f.severity is ThreatSeverity.CRITICAL)

    @property
    def high_findings(self) -> int:
        """Count of high-severity findings."""
        return sum(1 for f in self.findings if f.severity is ThreatSeverity.HIGH)

    @property
    def resolved_count(self) -> int:
        """Count of resolved findings."""
        return sum(1 for f in self.findings if f.status is ThreatStatus.RESOLVED)

    @property
    def open_count(self) -> int:
        """Count of open findings."""
        return sum(1 for f in self.findings if f.status is ThreatStatus.OPEN)

    @property
    def has_blocking_findings(self) -> bool:
        """True if any critical or high findings are open.

        Per Section 17 Phase 09 mandatory acceptance: critical findings
        resolved or release blocked.
        """
        return any(
            f.severity in (ThreatSeverity.CRITICAL, ThreatSeverity.HIGH)
            and f.status is ThreatStatus.OPEN
            for f in self.findings
        )


# ── Security Scan ──


class ScanType(StrEnum):
    """Type of security scan (deliverable 2)."""

    SECRET_SCAN = "secret_scan"
    DEPENDENCY_SCAN = "dependency_scan"
    STATIC_ANALYSIS = "static_analysis"
    TENANT_ISOLATION_SCAN = "tenant_isolation_scan"


class ScanStatus(StrEnum):
    """Status of a security scan."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ScanId:
    """Stable identity for a security scan run."""

    value: UUID

    @classmethod
    def generate(cls) -> ScanId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ScanResult:
    """Result of a security scan (deliverable 2).

    Per AD-010: security scanning across all components.
    Per AD-022: security audit evidence.

    Attributes:
        scan_id: Stable unique identifier.
        scan_type: Type of scan performed.
        component: Component scanned.
        status: Pass/fail/skip status.
        findings_count: Number of findings (0 = clean).
        findings: List of finding descriptions (empty if clean).
        scanned_at: UTC scan timestamp.
    """

    scan_id: ScanId
    scan_type: ScanType
    component: str
    status: ScanStatus
    findings_count: int = 0
    findings: list[str] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.component:
            raise ValueError("component must not be empty.")
        if self.findings_count < 0:
            raise ValueError("findings_count must be non-negative.")
        if self.findings_count != len(self.findings):
            raise ValueError("findings_count must equal len(findings).")
        if self.scanned_at.tzinfo is None:
            raise ValueError("scanned_at must be timezone-aware (UTC).")
        if self.status is ScanStatus.PASSED and self.findings_count > 0:
            raise ValueError("PASSED scan must have 0 findings.")

    @classmethod
    def pass_scan(
        cls,
        scan_type: ScanType,
        component: str,
    ) -> ScanResult:
        """Create a passing scan result with 0 findings."""
        return cls(
            scan_id=ScanId.generate(),
            scan_type=scan_type,
            component=component,
            status=ScanStatus.PASSED,
            findings_count=0,
            findings=[],
        )

    @classmethod
    def fail_scan(
        cls,
        scan_type: ScanType,
        component: str,
        findings: list[str],
    ) -> ScanResult:
        """Create a failing scan result with findings."""
        return cls(
            scan_id=ScanId.generate(),
            scan_type=scan_type,
            component=component,
            status=ScanStatus.FAILED,
            findings_count=len(findings),
            findings=findings,
        )


# ── Backup and Recovery ──


class BackupType(StrEnum):
    """Type of backup (deliverable 6).

    Per AD-028: tested backups, point-in-time recovery.
    """

    FULL = "full"
    INCREMENTAL = "incremental"
    SNAPSHOT = "snapshot"


class BackupStatus(StrEnum):
    """Status of a backup."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    RESTORED = "restored"


@dataclass(frozen=True)
class BackupId:
    """Stable identity for a backup."""

    value: UUID

    @classmethod
    def generate(cls) -> BackupId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class BackupRecord:
    """A backup record (deliverable 6).

    Per AD-028: tested backups, point-in-time recovery, backup
    restoration tests.

    Attributes:
        backup_id: Stable unique identifier.
        tenant_id: Tenant scope (or "system" for system-wide backups).
        backup_type: Type of backup.
        status: Backup lifecycle status.
        created_at: UTC creation timestamp.
        completed_at: UTC completion timestamp (None if pending).
        restored_at: UTC restoration timestamp (None if not restored).
        data_checksum: Checksum of the backed-up data.
        size_bytes: Size of the backup in bytes.
        metadata: Additional backup metadata.
    """

    backup_id: BackupId
    tenant_id: str
    backup_type: BackupType
    status: BackupStatus = BackupStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    restored_at: datetime | None = None
    data_checksum: str = ""
    size_bytes: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware (UTC).")
        if self.restored_at is not None and self.restored_at.tzinfo is None:
            raise ValueError("restored_at must be timezone-aware (UTC).")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative.")

    def complete(
        self,
        data_checksum: str,
        size_bytes: int,
    ) -> BackupRecord:
        """Mark the backup as completed."""
        return BackupRecord(
            backup_id=self.backup_id,
            tenant_id=self.tenant_id,
            backup_type=self.backup_type,
            status=BackupStatus.COMPLETED,
            created_at=self.created_at,
            completed_at=datetime.now(UTC),
            data_checksum=data_checksum,
            size_bytes=size_bytes,
            metadata=self.metadata,
        )

    def restore(self) -> BackupRecord:
        """Mark the backup as restored (deliverable 6).

        Per AD-028: backup restoration tests.
        """
        if self.status is not BackupStatus.COMPLETED:
            raise ValueError(f"Cannot restore backup in status {self.status.value}.")
        return BackupRecord(
            backup_id=self.backup_id,
            tenant_id=self.tenant_id,
            backup_type=self.backup_type,
            status=BackupStatus.RESTORED,
            created_at=self.created_at,
            completed_at=self.completed_at,
            restored_at=datetime.now(UTC),
            data_checksum=self.data_checksum,
            size_bytes=self.size_bytes,
            metadata=self.metadata,
        )


# ── Disaster Recovery ──


class RecoveryPhase(StrEnum):
    """Phases of disaster recovery (deliverable 7).

    Per AD-017: SAFE_HALT, reconciliation, human authorization.
    Per AD-028: multi-AZ resilience, execution ownership controls,
    reconciliation before trading resumes.

    Critical principle: Infrastructure recovery does NOT authorize
    trading recovery (Section 12).
    """

    INFRASTRUCTURE_RECOVERY = "infrastructure_recovery"
    DATA_RECONCILIATION = "data_reconciliation"
    HUMAN_AUTHORIZATION = "human_authorization"
    TRADING_RESUMPTION = "trading_resumption"
    COMPLETED = "completed"


@dataclass(frozen=True)
class RecoveryId:
    """Stable identity for a disaster recovery process."""

    value: UUID

    @classmethod
    def generate(cls) -> RecoveryId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class DisasterRecoveryState:
    """Disaster recovery state machine (deliverable 7).

    Per AD-017: critical trading failures require SAFE_HALT,
    reconciliation, and human authorization before resumption.
    Per AD-028: execution ownership controls, reconciliation before
    trading resumes.
    Per Section 12: infrastructure recovery does NOT authorize
    trading recovery. Cloud restart must never silently restore
    live trading after a critical failure.

    The recovery process MUST proceed through each phase in order:
    1. INFRASTRUCTURE_RECOVERY — services restarted, data restored
    2. DATA_RECONCILIATION — financial records reconciled
    3. HUMAN_AUTHORIZATION — explicit owner approval for trading
    4. TRADING_RESUMPTION — trading enabled after authorization
    5. COMPLETED — recovery complete

    Skipping HUMAN_AUTHORIZATION is prohibited.
    """

    recovery_id: RecoveryId
    tenant_id: str
    phase: RecoveryPhase = RecoveryPhase.INFRASTRUCTURE_RECOVERY
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    phase_started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    human_authorized: bool = False
    reconciliation_completed: bool = False
    completed_at: datetime | None = None
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.phase_started_at.tzinfo is None:
            raise ValueError("phase_started_at must be timezone-aware (UTC).")

    @property
    def is_complete(self) -> bool:
        """True if recovery is complete."""
        return self.phase is RecoveryPhase.COMPLETED

    @property
    def is_infra_recovered(self) -> bool:
        """True if infrastructure recovery is done."""
        return self.phase != RecoveryPhase.INFRASTRUCTURE_RECOVERY

    def advance_to_reconciliation(self) -> DisasterRecoveryState:
        """Advance to data reconciliation phase."""
        with self._lock:
            if self.phase is not RecoveryPhase.INFRASTRUCTURE_RECOVERY:
                raise ValueError(f"Cannot advance to reconciliation from {self.phase.value}.")
            return DisasterRecoveryState(
                recovery_id=self.recovery_id,
                tenant_id=self.tenant_id,
                phase=RecoveryPhase.DATA_RECONCILIATION,
                started_at=self.started_at,
                phase_started_at=datetime.now(UTC),
                human_authorized=False,
                reconciliation_completed=False,
            )

    def complete_reconciliation(self) -> DisasterRecoveryState:
        """Complete data reconciliation and advance to human authorization."""
        with self._lock:
            if self.phase is not RecoveryPhase.DATA_RECONCILIATION:
                raise ValueError(f"Cannot complete reconciliation from {self.phase.value}.")
            return DisasterRecoveryState(
                recovery_id=self.recovery_id,
                tenant_id=self.tenant_id,
                phase=RecoveryPhase.HUMAN_AUTHORIZATION,
                started_at=self.started_at,
                phase_started_at=datetime.now(UTC),
                human_authorized=False,
                reconciliation_completed=True,
            )

    def grant_human_authorization(self) -> DisasterRecoveryState:
        """Grant human authorization for trading resumption.

        Per Section 12: human-controlled trading recovery.
        Per AD-017: human authorization before resumption.
        """
        with self._lock:
            if self.phase is not RecoveryPhase.HUMAN_AUTHORIZATION:
                raise ValueError(f"Cannot grant authorization from {self.phase.value}.")
            if not self.reconciliation_completed:
                raise ValueError("Cannot authorize trading before reconciliation completes.")
            return DisasterRecoveryState(
                recovery_id=self.recovery_id,
                tenant_id=self.tenant_id,
                phase=RecoveryPhase.TRADING_RESUMPTION,
                started_at=self.started_at,
                phase_started_at=datetime.now(UTC),
                human_authorized=True,
                reconciliation_completed=True,
            )

    def complete(self) -> DisasterRecoveryState:
        """Complete the recovery process."""
        with self._lock:
            if self.phase is not RecoveryPhase.TRADING_RESUMPTION:
                raise ValueError(f"Cannot complete from {self.phase.value}.")
            if not self.human_authorized:
                raise ValueError("Cannot complete recovery without human authorization.")
            return DisasterRecoveryState(
                recovery_id=self.recovery_id,
                tenant_id=self.tenant_id,
                phase=RecoveryPhase.COMPLETED,
                started_at=self.started_at,
                phase_started_at=self.phase_started_at,
                human_authorized=True,
                reconciliation_completed=True,
                completed_at=datetime.now(UTC),
            )

    def skip_to_trading(self) -> DisasterRecoveryState:
        """Attempt to skip human authorization — MUST be rejected.

        Per Section 12: infrastructure recovery does NOT authorize
        trading recovery. This method always raises to prove the
        invariant is enforced.
        """
        raise ValueError(
            "Skipping human authorization is prohibited. "
            "Infrastructure recovery does NOT authorize trading recovery."
        )


# ── Split-Brain Detection ──


class SplitBrainRole(StrEnum):
    """Role of a node in a split-brain scenario (deliverable 8).

    Per AD-016: event-driven multi-tenant cloud.
    Per AD-028: split-brain protection.
    """

    PRIMARY = "primary"
    SECONDARY = "secondary"
    ISOLATED = "isolated"


@dataclass(frozen=True)
class NodeId:
    """Stable identity for a cluster node."""

    value: UUID

    @classmethod
    def generate(cls) -> NodeId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class NodeState:
    """State of a single cluster node (deliverable 8).

    Per AD-028: split-brain protection.

    Attributes:
        node_id: Stable unique identifier.
        role: Primary, secondary, or isolated.
        is_alive: True if the node is reachable.
        last_heartbeat: UTC timestamp of last heartbeat.
        quorum_member: True if this node believes it has quorum.
        lease_expires_at: UTC timestamp when the node's lease expires.
    """

    node_id: NodeId
    role: SplitBrainRole = SplitBrainRole.SECONDARY
    is_alive: bool = True
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(UTC))
    quorum_member: bool = True
    lease_expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(seconds=30)
    )

    def __post_init__(self) -> None:
        if self.last_heartbeat.tzinfo is None:
            raise ValueError("last_heartbeat must be timezone-aware (UTC).")
        if self.lease_expires_at.tzinfo is None:
            raise ValueError("lease_expires_at must be timezone-aware (UTC).")

    @property
    def lease_expired(self) -> bool:
        """True if the node's lease has expired."""
        return datetime.now(UTC) >= self.lease_expires_at

    def heartbeat(self) -> NodeState:
        """Record a heartbeat and extend the lease."""
        return NodeState(
            node_id=self.node_id,
            role=self.role,
            is_alive=True,
            last_heartbeat=datetime.now(UTC),
            quorum_member=self.quorum_member,
            lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
        )

    def mark_dead(self) -> NodeState:
        """Mark the node as dead."""
        return NodeState(
            node_id=self.node_id,
            role=self.role,
            is_alive=False,
            last_heartbeat=self.last_heartbeat,
            quorum_member=False,
            lease_expires_at=self.lease_expires_at,
        )


@dataclass
class SplitBrainDetection:
    """Split-brain detection result (deliverable 8).

    Per AD-028: split-brain protection.
    Per Section 12: split-brain protection.

    A split-brain is detected when two or more nodes both believe
    they are PRIMARY with quorum. The detection determines which
    node should remain active and which should be fenced.

    Attributes:
        detection_id: Stable unique identifier.
        nodes: All node states in the cluster.
        detected: True if a split-brain was detected.
        active_node_id: ID of the node that should remain active.
        fenced_node_ids: IDs of nodes that should be fenced.
        detected_at: UTC detection timestamp.
    """

    detection_id: UUID
    nodes: list[NodeState]
    detected: bool = False
    active_node_id: NodeId | None = None
    fenced_node_ids: list[NodeId] = field(default_factory=list)
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("nodes must not be empty.")
        if self.detected_at.tzinfo is None:
            raise ValueError("detected_at must be timezone-aware (UTC).")

    @property
    def primary_count(self) -> int:
        """Count of nodes claiming the PRIMARY role."""
        return sum(
            1
            for n in self.nodes
            if n.role is SplitBrainRole.PRIMARY and n.quorum_member and n.is_alive
        )

    @property
    def is_split_brain(self) -> bool:
        """True if multiple live primaries with quorum exist."""
        return self.primary_count > 1


# ── Fault Injection ──


class FaultType(StrEnum):
    """Type of injected fault (deliverable 9).

    Per AD-023: fault injection and repeatable verification.
    """

    NETWORK_TIMEOUT = "network_timeout"
    EXCHANGE_ERROR = "exchange_error"
    DATABASE_FAILURE = "database_failure"
    LATENCY_SPIKE = "latency_spike"
    PARTIAL_FAILURE = "partial_failure"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


class FaultInjectionStatus(StrEnum):
    """Status of a fault injection test."""

    INJECTED = "injected"
    RECOVERED = "recovered"
    DETECTED = "detected"
    UNDETECTED = "undetected"


@dataclass(frozen=True)
class FaultId:
    """Stable identity for a fault injection."""

    value: UUID

    @classmethod
    def generate(cls) -> FaultId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class FaultInjectionResult:
    """Result of a fault injection test (deliverable 9).

    Per AD-023: fault injection and repeatable verification
    before live operations.

    Attributes:
        fault_id: Stable unique identifier.
        fault_type: Type of fault injected.
        target_component: Component that received the fault.
        status: Whether the fault was detected and recovered.
        detection_time_ms: Time to detect the fault in milliseconds.
        recovery_time_ms: Time to recover from the fault in milliseconds.
        injected_at: UTC injection timestamp.
        recovered_at: UTC recovery timestamp (None if not recovered).
        evidence: Description of what was observed.
    """

    fault_id: FaultId
    fault_type: FaultType
    target_component: str
    status: FaultInjectionStatus
    detection_time_ms: float = 0.0
    recovery_time_ms: float = 0.0
    injected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    recovered_at: datetime | None = None
    evidence: str = ""

    def __post_init__(self) -> None:
        if not self.target_component:
            raise ValueError("target_component must not be empty.")
        if self.detection_time_ms < 0:
            raise ValueError("detection_time_ms must be non-negative.")
        if self.recovery_time_ms < 0:
            raise ValueError("recovery_time_ms must be non-negative.")
        if self.injected_at.tzinfo is None:
            raise ValueError("injected_at must be timezone-aware (UTC).")
        if self.recovered_at is not None and self.recovered_at.tzinfo is None:
            raise ValueError("recovered_at must be timezone-aware (UTC).")
        if self.status is FaultInjectionStatus.RECOVERED and self.recovered_at is None:
            raise ValueError("recovered_at must be set when status is RECOVERED.")

    @property
    def was_detected(self) -> bool:
        """True if the fault was detected."""
        return self.status in (
            FaultInjectionStatus.DETECTED,
            FaultInjectionStatus.RECOVERED,
        )

    @property
    def was_recovered(self) -> bool:
        """True if the system recovered from the fault."""
        return self.status is FaultInjectionStatus.RECOVERED


# ── Load Testing ──


@dataclass(frozen=True)
class LoadTestId:
    """Stable identity for a load test run."""

    value: UUID

    @classmethod
    def generate(cls) -> LoadTestId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class LoadTestResult:
    """Result of a load test (deliverable 10).

    Per AD-016: event-driven multi-tenant cloud.
    Per Section 14.1: design for 10,000 users. Actual concurrency,
    throughput, and latency must be established through measured
    benchmarks.

    Attributes:
        test_id: Stable unique identifier.
        target_rps: Target requests per second.
        actual_rps: Achieved requests per second.
        total_requests: Total requests sent.
        successful_requests: Requests that succeeded.
        failed_requests: Requests that failed.
        p50_latency_ms: 50th percentile latency in ms.
        p95_latency_ms: 95th percentile latency in ms.
        p99_latency_ms: 99th percentile latency in ms.
        duration_seconds: Test duration in seconds.
        started_at: UTC start timestamp.
    """

    test_id: LoadTestId
    target_rps: int
    actual_rps: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    duration_seconds: float
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.target_rps <= 0:
            raise ValueError("target_rps must be positive.")
        if self.actual_rps < 0:
            raise ValueError("actual_rps must be non-negative.")
        if self.total_requests < 0:
            raise ValueError("total_requests must be non-negative.")
        if self.successful_requests < 0:
            raise ValueError("successful_requests must be non-negative.")
        if self.failed_requests < 0:
            raise ValueError("failed_requests must be non-negative.")
        if self.successful_requests + self.failed_requests != self.total_requests:
            raise ValueError("successful_requests + failed_requests must equal total_requests.")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive.")
        if self.p50_latency_ms < 0:
            raise ValueError("p50_latency_ms must be non-negative.")
        if self.p95_latency_ms < 0:
            raise ValueError("p95_latency_ms must be non-negative.")
        if self.p99_latency_ms < 0:
            raise ValueError("p99_latency_ms must be non-negative.")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")

    @property
    def success_rate(self) -> float:
        """Fraction of requests that succeeded (0.0 to 1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def meets_p95_target(self) -> bool:
        """True if p95 latency is under 500ms (Section 14.2 target)."""
        MAX_WRITE_P95_MS = 500.0
        return self.p95_latency_ms <= MAX_WRITE_P95_MS

    @property
    def meets_read_p95_target(self) -> bool:
        """True if p95 latency is under 300ms (Section 14.2 read target)."""
        MAX_READ_P95_MS = 300.0
        return self.p95_latency_ms <= MAX_READ_P95_MS


# ── Observability ──


class MetricType(StrEnum):
    """Type of observability metric (deliverable 11).

    Per AD-022: operational metrics, financial reconciliation
    metrics, risk decision records.
    """

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass(frozen=True)
class MetricId:
    """Stable identity for an observability metric."""

    value: UUID

    @classmethod
    def generate(cls) -> MetricId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ObservabilityMetric:
    """A single observability metric (deliverable 11).

    Per AD-022: structured logs, distributed traces, operational
    metrics, financial reconciliation metrics, risk decision
    records, policy version tracking, security audit events,
    incident records.

    Attributes:
        metric_id: Stable unique identifier.
        name: Metric name (e.g., "risk.assessments.total").
        metric_type: Type of metric.
        value: Current value.
        unit: Unit of measurement.
        labels: Dimensional labels for filtering.
        timestamp: UTC measurement timestamp.
    """

    metric_id: MetricId
    name: str
    metric_type: MetricType
    value: float
    unit: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class ObservabilityReport:
    """Observability verification report (deliverable 11).

    Per AD-022: verify structured logs, distributed traces,
    operational metrics, financial reconciliation metrics, risk
    decision records, policy version tracking, security audit
    events, incident records, and alerting.

    Attributes:
        report_id: Stable unique identifier.
        metrics: All verified metrics.
        log_entries_verified: Count of structured log entries verified.
        trace_entries_verified: Count of distributed trace entries verified.
        audit_events_verified: Count of security audit events verified.
        created_at: UTC creation timestamp.
    """

    report_id: UUID
    metrics: list[ObservabilityMetric] = field(default_factory=list)
    log_entries_verified: int = 0
    trace_entries_verified: int = 0
    audit_events_verified: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.log_entries_verified < 0:
            raise ValueError("log_entries_verified must be non-negative.")
        if self.trace_entries_verified < 0:
            raise ValueError("trace_entries_verified must be non-negative.")
        if self.audit_events_verified < 0:
            raise ValueError("audit_events_verified must be non-negative.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    @property
    def all_verified(self) -> bool:
        """True if all observability categories are present."""
        MIN_METRICS = 1
        return (
            len(self.metrics) >= MIN_METRICS
            and self.log_entries_verified > 0
            and self.trace_entries_verified > 0
            and self.audit_events_verified > 0
        )


# ── Cost and Token Evaluation ──


@dataclass(frozen=True)
class CostEvaluationId:
    """Stable identity for a cost evaluation."""

    value: UUID

    @classmethod
    def generate(cls) -> CostEvaluationId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class CostEvaluation:
    """Cost and token evaluation report (deliverable 12).

    Per AD-025: enforce bounded LLM usage, tenant quotas, rate
    limits, and infrastructure cost controls without weakening
    safety.

    Per Section 14.3: cost governance — deterministic-first
    processing, bounded LLM calls, tenant quotas, rate limits,
    shared eligible public-data processing, noncritical async
    jobs, cost monitoring, resource budgets.

    Attributes:
        evaluation_id: Stable unique identifier.
        tenant_id: Tenant scope.
        llm_tokens_used: Total LLM tokens consumed.
        llm_tokens_limit: Daily token limit.
        llm_cost_usd: Estimated LLM cost in USD.
        infrastructure_cost_usd: Infrastructure cost in USD.
        deterministic_calls: Deterministic processing calls.
        llm_calls: LLM gateway calls.
        cost_ratio: Ratio of LLM cost to total cost (0.0-1.0).
        within_budget: True if costs are within budget.
        evaluated_at: UTC evaluation timestamp.
    """

    evaluation_id: CostEvaluationId
    tenant_id: str
    llm_tokens_used: int = 0
    llm_tokens_limit: int = 10000
    llm_cost_usd: float = 0.0
    infrastructure_cost_usd: float = 0.0
    deterministic_calls: int = 0
    llm_calls: int = 0
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.llm_tokens_used < 0:
            raise ValueError("llm_tokens_used must be non-negative.")
        if self.llm_tokens_limit <= 0:
            raise ValueError("llm_tokens_limit must be positive.")
        if self.llm_cost_usd < 0:
            raise ValueError("llm_cost_usd must be non-negative.")
        if self.infrastructure_cost_usd < 0:
            raise ValueError("infrastructure_cost_usd must be non-negative.")
        if self.deterministic_calls < 0:
            raise ValueError("deterministic_calls must be non-negative.")
        if self.llm_calls < 0:
            raise ValueError("llm_calls must be non-negative.")
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware (UTC).")

    @property
    def token_utilization_pct(self) -> float:
        """Fraction of token budget used (0.0 to 100.0)."""
        return (self.llm_tokens_used / self.llm_tokens_limit) * 100.0

    @property
    def total_cost_usd(self) -> float:
        """Total cost (LLM + infrastructure)."""
        return self.llm_cost_usd + self.infrastructure_cost_usd

    @property
    def cost_ratio(self) -> float:
        """Ratio of LLM cost to total cost (0.0 to 1.0)."""
        if self.total_cost_usd == 0:
            return 0.0
        return self.llm_cost_usd / self.total_cost_usd

    @property
    def within_budget(self) -> bool:
        """True if token usage is within budget.

        Per AD-025: cost optimization must never disable mandatory
        safety or financial controls.
        """
        return self.llm_tokens_used <= self.llm_tokens_limit

    @property
    def deterministic_ratio(self) -> float:
        """Ratio of deterministic calls to total calls (AD-003)."""
        total = self.deterministic_calls + self.llm_calls
        if total == 0:
            return 0.0
        return self.deterministic_calls / total

    @property
    def meets_deterministic_first_target(self) -> bool:
        """True if deterministic-first processing dominates (AD-003).

        Per AD-003: routine financial processing shall use
        deterministic algorithms. LLM usage must remain bounded.
        """
        DETERMINISTIC_RATIO_THRESHOLD = 0.8
        return self.deterministic_ratio >= DETERMINISTIC_RATIO_THRESHOLD
