"""Evidence and assurance contracts for Kian Trading Intelligence.

Per E8 (Evidence and Assurance):

Decision ledger, decision dossiers, OpenTelemetry-style instrumentation,
SLO monitoring, living threat model, SBOM (CycloneDX), SLSA provenance,
Sigstore-style signing (HMAC-simulated), API fuzzing, CI badge generation,
verifier CLI, and game-day drills.

These contracts are leaf-level — they must NOT import from services or
simulation (import-linter contracts-is-leaf).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

# ── Decision Ledger ────────────────────────────────────────────────


@dataclass(frozen=True)
class LedgerEntryId:
    """Stable identity for a decision ledger entry."""

    value: UUID

    @classmethod
    def generate(cls) -> LedgerEntryId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class LedgerEntry:
    """A single entry in the hash-chained decision ledger.

    Each entry links to the previous entry's hash, forming a
    tamper-evident chain. Any insertion, deletion, or modification
    breaks the chain and is detectable by verify_chain().

    Attributes:
        entry_id: Unique entry identifier.
        trade_id: Trade or decision identifier this entry pertains to.
        decision_type: Type of decision (e.g. entry, exit, adjust).
        payload: JSON-serialisable decision payload.
        previous_hash: Hash of the previous entry (genesis = "genesis").
        timestamp: UTC entry timestamp.
        entry_hash: SHA-256 hash of this entry (computed from fields).
        external_anchor: Optional URL of an external timestamping anchor.
    """

    entry_id: LedgerEntryId
    trade_id: str
    decision_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    previous_hash: str = "genesis"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    entry_hash: str = ""
    external_anchor: str | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if not self.trade_id:
            raise ValueError("trade_id must not be empty.")
        if not self.decision_type:
            raise ValueError("decision_type must not be empty.")
        if self.entry_hash == "":
            self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = {
            "entry_id": str(self.entry_id),
            "trade_id": self.trade_id,
            "decision_type": self.decision_type,
            "payload": json.dumps(self.payload, sort_keys=True, default=str),
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp.isoformat(),
        }
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DossierId:
    """Stable identity for a decision dossier."""

    value: UUID

    @classmethod
    def generate(cls) -> DossierId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class DecisionDossier:
    """Per-trade decision dossier assembled from ledger entries.

    Attributes:
        dossier_id: Unique dossier identifier.
        trade_id: Trade this dossier covers.
        entries: Ledger entries relevant to this trade.
        created_at: UTC creation timestamp.
        summary: JSON-serialisable summary of the decision trail.
        dossier_hash: SHA-256 hash of the dossier contents.
    """

    dossier_id: DossierId
    trade_id: str
    entries: list[LedgerEntry] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    summary: dict[str, Any] = field(default_factory=dict)
    dossier_hash: str = ""

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if not self.trade_id:
            raise ValueError("trade_id must not be empty.")
        if self.dossier_hash == "":
            self.dossier_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = {
            "dossier_id": str(self.dossier_id),
            "trade_id": self.trade_id,
            "entry_hashes": [e.entry_hash for e in self.entries],
            "created_at": self.created_at.isoformat(),
            "summary": json.dumps(self.summary, sort_keys=True, default=str),
        }
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── OpenTelemetry-style Instrumentation ───────────────────────────


class SpanKind(StrEnum):
    """Kind of OpenTelemetry span."""

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


@dataclass
class SpanRecord:
    """A single recorded span (simulated OTel span).

    Attributes:
        span_id: Unique span identifier.
        trace_id: Trace identifier this span belongs to.
        parent_span_id: Parent span identifier (None for root).
        name: Span name.
        kind: Span kind.
        start_time: UTC start timestamp.
        end_time: UTC end timestamp (None if still open).
        attributes: Span attributes.
        status: Span status (ok, error).
    """

    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str
    kind: SpanKind = SpanKind.INTERNAL
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is None:
            raise ValueError("start_time must be timezone-aware (UTC).")


@dataclass
class MetricRecord:
    """A single recorded metric value (simulated OTel metric).

    Attributes:
        name: Metric name.
        value: Metric value.
        unit: Metric unit.
        timestamp: UTC recording timestamp.
        attributes: Metric attributes.
    """

    name: str
    value: float
    unit: str = "1"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class OTelConfig:
    """Configuration for OpenTelemetry-style instrumentation.

    Attributes:
        service_name: Service name reported in traces/metrics.
        service_version: Service version string.
        enabled: Whether instrumentation is enabled.
        trace_exporter: Trace exporter type (console, otlp, none).
        metric_exporter: Metric exporter type.
        sampling_rate: Trace sampling rate (0.0 – 1.0).
        resource_attributes: Resource attributes.
    """

    service_name: str = "kian-trading-intelligence"
    service_version: str = "0.1.0"
    enabled: bool = True
    trace_exporter: str = "console"
    metric_exporter: str = "console"
    sampling_rate: float = 1.0
    resource_attributes: dict[str, str] = field(default_factory=dict)


# ── SLO Monitoring ─────────────────────────────────────────────────


@dataclass
class SLODefinition:
    """Definition of a Service Level Objective.

    Attributes:
        name: SLO name (unique key).
        target: Target SLO fraction (e.g. 0.999 for 99.9%).
        window: SLO window in seconds (reporting period).
        description: Human-readable description.
    """

    name: str
    target: float
    window: int = 86400
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty.")
        if not (0.0 < self.target < 1.0):
            raise ValueError("target must be between 0 and 1 (exclusive).")

    @property
    def error_budget(self) -> float:
        """Error budget fraction = 1 - target_slo."""
        return 1.0 - self.target


@dataclass
class SLORequest:
    """A single request observation for SLO monitoring.

    Attributes:
        slo_name: SLO this request counts toward.
        success: Whether the request was successful.
        latency_ms: Request latency in milliseconds.
        timestamp: UTC observation timestamp.
    """

    slo_name: str
    success: bool
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class SLOBurnRateResult:
    """Burn-rate calculation result for an SLO.

    burn_rate = error_rate / error_budget
    where error_budget = 1 - target_slo_fraction

    Attributes:
        slo_name: SLO name.
        error_rate: Observed error rate (0.0 – 1.0).
        error_budget: Allowed error budget fraction.
        burn_rate: Computed burn rate.
        alerting: Whether burn rate exceeds the alerting threshold (1.0).
        window_seconds: Window used for calculation.
    """

    slo_name: str
    error_rate: float
    error_budget: float
    burn_rate: float
    alerting: bool
    window_seconds: int


class SLOAlertLevel(StrEnum):
    """Alert severity for SLO burn-rate violations."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SLOAlert:
    """An SLO burn-rate alert.

    Attributes:
        slo_name: SLO name.
        level: Alert level.
        burn_rate: Current burn rate.
        message: Human-readable alert message.
        timestamp: UTC alert timestamp.
    """

    slo_name: str
    level: SLOAlertLevel
    burn_rate: float
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


# ── Living Threat Model ────────────────────────────────────────────


class ThreatSeverity(StrEnum):
    """Severity level for a threat model entry."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatStatus(StrEnum):
    """Status of a threat model entry."""

    OPEN = "open"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"
    RETIRED = "retired"


@dataclass(frozen=True)
class ThreatModelEntryId:
    """Stable identity for a threat model entry."""

    value: UUID

    @classmethod
    def generate(cls) -> ThreatModelEntryId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ThreatModelEntry:
    """An entry in the living threat model.

    Attributes:
        entry_id: Unique entry identifier.
        component: Affected component or system.
        threat: Threat description.
        severity: Threat severity.
        status: Threat status (open, mitigated, accepted, retired).
        mitigation: Mitigation description (empty if none).
        updated_at: UTC last-update timestamp.
        metadata: Additional metadata.
    """

    entry_id: ThreatModelEntryId
    component: str
    threat: str
    severity: ThreatSeverity = ThreatSeverity.MEDIUM
    status: ThreatStatus = ThreatStatus.OPEN
    mitigation: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware (UTC).")
        if not self.component:
            raise ValueError("component must not be empty.")
        if not self.threat:
            raise ValueError("threat must not be empty.")


@dataclass
class ThreatModelReport:
    """Full threat model export.

    Attributes:
        entries: All threat model entries.
        generated_at: UTC generation timestamp.
        total: Total entries.
        open_count: Number of open entries.
        by_severity: Count per severity.
        by_status: Count per status.
    """

    entries: list[ThreatModelEntry]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    total: int = 0
    open_count: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware (UTC).")


# ── SBOM (CycloneDX) ───────────────────────────────────────────────


@dataclass
class SBOMComponent:
    """A single component in a Software Bill of Materials (CycloneDX).

    Attributes:
        name: Component name.
        version: Component version.
        type: Component type (application, library, framework, etc.).
        purl: Package URL (purl).
        bom_ref: BOM reference identifier.
        hashes: Component hashes (e.g. {"SHA256": "..."}).
        supplier: Supplier / author.
    """

    name: str
    version: str
    type: str = "library"
    purl: str = ""
    bom_ref: str = ""
    hashes: dict[str, str] = field(default_factory=dict)
    supplier: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty.")


@dataclass
class SBOMDocument:
    """A CycloneDX-style Software Bill of Materials document.

    Attributes:
        bom_format: Always "CycloneDX".
        spec_version: CycloneDX spec version.
        components: List of components.
        serial_number: BOM serial number (UUID).
        metadata: BOM metadata (timestamp, tools, supplier).
    """

    bom_format: str = "CycloneDX"
    spec_version: str = "1.5"
    components: list[SBOMComponent] = field(default_factory=list)
    serial_number: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation suitable for JSON serialisation."""
        return {
            "bomFormat": self.bom_format,
            "specVersion": self.spec_version,
            "serialNumber": self.serial_number,
            "metadata": self.metadata,
            "components": [
                {
                    "name": c.name,
                    "version": c.version,
                    "type": c.type,
                    "purl": c.purl,
                    "bomRef": c.bom_ref,
                    "hashes": c.hashes,
                    "supplier": c.supplier,
                }
                for c in self.components
            ],
        }


# ── SLSA Provenance ───────────────────────────────────────────────


@dataclass
class SLSABuildInfo:
    """Build information for SLSA provenance.

    Attributes:
        builder_id: Builder identity.
        build_type: Build type (e.g. "github-actions").
        build_invocation_id: Unique build invocation ID.
        build_started_at: UTC build start timestamp.
        build_finished_at: UTC build finish timestamp.
        source_uri: Source repository URI.
        source_branch: Source branch or ref.
        source_commit: Source commit SHA.
    """

    builder_id: str = ""
    build_type: str = ""
    build_invocation_id: str = ""
    build_started_at: datetime | None = None
    build_finished_at: datetime | None = None
    source_uri: str = ""
    source_branch: str = ""
    source_commit: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation."""
        return {
            "builderId": self.builder_id,
            "buildType": self.build_type,
            "buildInvocationId": self.build_invocation_id,
            "buildStartedAt": (
                self.build_started_at.isoformat() if self.build_started_at else None
            ),
            "buildFinishedAt": (
                self.build_finished_at.isoformat() if self.build_finished_at else None
            ),
            "sourceUri": self.source_uri,
            "sourceBranch": self.source_branch,
            "sourceCommit": self.source_commit,
        }


@dataclass
class SLSAMaterial:
    """A material (input artifact) in SLSA provenance.

    Attributes:
        uri: Material URI.
        digest: Material digest (e.g. {"sha256": "..."}).
    """

    uri: str
    digest: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation."""
        return {"uri": self.uri, "digest": self.digest}


@dataclass
class SLSAProvenance:
    """SLSA provenance statement.

    Attributes:
        build_info: Build information.
        materials: List of materials.
        subject: Subject (the built artifact) digest.
        provenance_hash: SHA-256 hash of the provenance statement.
        slsa_level: SLSA level (1-4).
        created_at: UTC creation timestamp.
    """

    build_info: SLSABuildInfo
    materials: list[SLSAMaterial] = field(default_factory=list)
    subject: dict[str, str] = field(default_factory=dict)
    provenance_hash: str = ""
    slsa_level: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if self.provenance_hash == "":
            self.provenance_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = {
            "build_info": json.dumps(
                self.build_info.to_dict(),
                sort_keys=True,
                default=str,
            ),
            "materials": json.dumps(
                [m.to_dict() for m in self.materials],
                sort_keys=True,
                default=str,
            ),
            "subject": json.dumps(self.subject, sort_keys=True, default=str),
            "slsa_level": self.slsa_level,
            "created_at": self.created_at.isoformat(),
        }
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation."""
        return {
            "buildInfo": self.build_info.to_dict(),
            "materials": [m.to_dict() for m in self.materials],
            "subject": self.subject,
            "provenanceHash": self.provenance_hash,
            "slsaLevel": self.slsa_level,
            "createdAt": self.created_at.isoformat(),
        }


# ── Sigstore-style Signing ────────────────────────────────────────


@dataclass
class SigningResult:
    """Result of signing an artifact (HMAC-SHA256 simulated).

    Attributes:
        artifact_hash: SHA-256 hash of the signed artifact.
        signature: HMAC-SHA256 signature (hex).
        signed_at: UTC signing timestamp.
        signer: Signer identity.
        key_id: Key identifier.
    """

    artifact_hash: str
    signature: str
    signed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    signer: str = "kian-evidence"
    key_id: str = "default"

    def __post_init__(self) -> None:
        if self.signed_at.tzinfo is None:
            raise ValueError("signed_at must be timezone-aware (UTC).")


@dataclass
class VerificationResult:
    """Result of verifying a signature or attestation.

    Attributes:
        valid: Whether verification succeeded.
        artifact_hash: Hash of the verified artifact.
        verified_at: UTC verification timestamp.
        message: Verification message.
    """

    valid: bool
    artifact_hash: str = ""
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str = ""

    def __post_init__(self) -> None:
        if self.verified_at.tzinfo is None:
            raise ValueError("verified_at must be timezone-aware (UTC).")


# ── API Fuzzing ───────────────────────────────────────────────────


class FuzzStatus(StrEnum):
    """Status of a fuzz test result."""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class FuzzEndpoint:
    """A registered endpoint for API fuzzing.

    Attributes:
        method: HTTP method (GET, POST, PUT, DELETE, etc.).
        path: Endpoint path (e.g. "/api/v1/trades").
        parameters: Expected parameters and their types.
        expected_status: Expected HTTP status code.
    """

    method: str
    path: str
    parameters: dict[str, str] = field(default_factory=dict)
    expected_status: int = 200

    def __post_init__(self) -> None:
        if not self.method:
            raise ValueError("method must not be empty.")
        if not self.path:
            raise ValueError("path must not be empty.")


@dataclass
class FuzzResult:
    """A single fuzz test result.

    Attributes:
        endpoint: Endpoint that was fuzzed.
        input: Fuzz input that was sent.
        status: Result status (ok, error, timeout).
        response_status: HTTP status code received (0 if no response).
        response_body: Response body (truncated).
        duration_ms: Duration in milliseconds.
        finding: Description of any finding (empty if none).
    """

    endpoint: FuzzEndpoint
    input: str
    status: FuzzStatus = FuzzStatus.OK
    response_status: int = 0
    response_body: str = ""
    duration_ms: float = 0.0
    finding: str = ""


@dataclass
class FuzzReport:
    """Full fuzz report.

    Attributes:
        results: All fuzz results.
        total: Total tests run.
        errors: Number of error-status results.
        timeouts: Number of timeout results.
        findings: Findings (non-empty finding field).
        generated_at: UTC report timestamp.
    """

    results: list[FuzzResult] = field(default_factory=list)
    total: int = 0
    errors: int = 0
    timeouts: int = 0
    findings: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware (UTC).")


# ── CI Badge Generation ────────────────────────────────────────────


class BadgeColor:
    """Standard badge colours by status."""

    GREEN = "brightgreen"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"
    BLUE = "blue"
    GREY = "lightgrey"


@dataclass
class Badge:
    """A CI status badge.

    Attributes:
        label: Badge label (left side).
        message: Badge message (right side).
        color: Badge colour.
        svg: Generated SVG string.
    """

    label: str
    message: str
    color: str = BadgeColor.GREEN
    svg: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("label must not be empty.")
        if not self.message:
            raise ValueError("message must not be empty.")
        if self.svg == "":
            self.svg = self._render_svg()

    def _render_svg(self) -> str:
        """Render a shields.io-style SVG badge."""
        label_w = max(len(self.label) * 7 + 10, 20)
        message_w = max(len(self.message) * 7 + 10, 20)
        total_w = label_w + message_w
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20">'
            f'<rect width="{label_w}" height="20" fill="#555"/>'
            f'<rect x="{label_w}" width="{message_w}" height="20" fill="#{self.color}"/>'
            f'<text x="{label_w // 2}" y="14" fill="#fff" font-size="10" '
            f'font-family="Verdana" text-anchor="middle">{self.label}</text>'
            f'<text x="{label_w + message_w // 2}" y="14" fill="#fff" font-size="10" '
            f'font-family="Verdana" text-anchor="middle">{self.message}</text>'
            f"</svg>"
        )


# ── Verifier CLI ──────────────────────────────────────────────────


class VerificationStatus(StrEnum):
    """Status of a verification operation."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class VerificationReport:
    """A verification report from the verifier CLI.

    Attributes:
        name: Verification name.
        status: Verification status (pass, fail, skip).
        message: Verification message.
        verified_at: UTC verification timestamp.
        details: Additional details.
    """

    name: str
    status: VerificationStatus
    message: str = ""
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.verified_at.tzinfo is None:
            raise ValueError("verified_at must be timezone-aware (UTC).")


# ── Game-Day Drills ────────────────────────────────────────────────


class DrillStatus(StrEnum):
    """Status of a game-day drill."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass(frozen=True)
class DrillId:
    """Stable identity for a game-day drill."""

    value: UUID

    @classmethod
    def generate(cls) -> DrillId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class DrillStep:
    """A single step in a game-day drill.

    Attributes:
        step_index: Step index (0-based).
        name: Step name.
        description: Step description.
        outcome: Step outcome (empty until recorded).
        timestamp: UTC step timestamp.
        duration_ms: Step duration in milliseconds.
    """

    step_index: int
    name: str
    description: str = ""
    outcome: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class GameDayRecord:
    """A full game-day drill record.

    Attributes:
        drill_id: Unique drill identifier.
        name: Drill name.
        scenario: Scenario description.
        steps: List of drill steps.
        status: Drill status.
        started_at: UTC start timestamp.
        completed_at: UTC completion timestamp (None if still running).
        findings: Findings from the drill.
        action_items: Action items from the drill.
    """

    drill_id: DrillId
    name: str
    scenario: str = ""
    steps: list[DrillStep] = field(default_factory=list)
    status: DrillStatus = DrillStatus.PLANNED
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    findings: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if not self.name:
            raise ValueError("name must not be empty.")
