"""Graduated autonomy, kill plane and compliance package contracts.

Per E9 (Graduated Autonomy, Kill Plane and Compliance Package):

Trust-level engine with signed approvals and automatic demotion (AD-038);
independent kill plane capable of cancelling orders and blocking new exposure
even if the main platform is down; operator cockpit; human-factors review of
dangerous actions; legal classification memo; data inventory, DPIA and
market-data terms register; external penetration test scaffold.

Architecture Decisions: AD-038 (Graduated Autonomy and Independent Kill Plane).

These contracts are leaf-level — they must NOT import from services or
simulation (import-linter contracts-is-leaf).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any
from uuid import UUID, uuid4

# ──────────────────────────────────────────────────────────────────────────────
# Trust levels  (AD-038: L0 observe → L5 higher-cap live)
# ──────────────────────────────────────────────────────────────────────────────


class TrustLevel(IntEnum):
    """Formal trust levels for graduated autonomy (AD-038).

    Agents operate at or below their assigned trust level.  Promotion requires
    a signed human approval; demotion is automatic on policy violation or
    anomaly detection.

    Attributes:
        L0_OBSERVE:       Read-only observation; no order capability.
        L1_PAPER:         Paper-trading orders only; no real capital.
        L2_SMALL_LIVE:    Live orders up to the small-cap threshold.
        L3_MEDIUM_LIVE:   Live orders up to the medium-cap threshold.
        L4_LARGE_LIVE:    Live orders up to the large-cap threshold.
        L5_HIGHER_CAP:    Highest authorised cap; requires explicit re-approval.
    """

    L0_OBSERVE = 0
    L1_PAPER = 1
    L2_SMALL_LIVE = 2
    L3_MEDIUM_LIVE = 3
    L4_LARGE_LIVE = 4
    L5_HIGHER_CAP = 5


class TrustLevelChangeReason(StrEnum):
    """Reason for a trust-level change event."""

    SIGNED_PROMOTION = "signed_promotion"
    AUTOMATIC_DEMOTION = "automatic_demotion"
    MANUAL_DEMOTION = "manual_demotion"
    SYSTEM_RESET = "system_reset"
    EMERGENCY_HALT = "emergency_halt"


@dataclass(frozen=True)
class TrustLevelApprovalId:
    """Stable identity for a trust-level promotion approval."""

    value: UUID

    @classmethod
    def generate(cls) -> TrustLevelApprovalId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class TrustLevelApproval:
    """A signed human approval to promote an agent to a higher trust level.

    Attributes:
        approval_id:     Unique approval identifier.
        agent_id:        The agent or tenant being approved.
        from_level:      Current trust level before promotion.
        to_level:        Target trust level (must be higher than from_level).
        approver_id:     Human approver identity.
        reason:          Human-readable justification.
        timestamp:       UTC timestamp of approval.
        approval_hash:   SHA-256 of all fields (tamper evidence).
        signature:       HMAC or external signature over approval_hash.
    """

    approval_id: TrustLevelApprovalId
    agent_id: str
    from_level: TrustLevel
    to_level: TrustLevel
    approver_id: str
    reason: str
    timestamp: datetime
    approval_hash: str
    signature: str

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.to_level <= self.from_level:
            raise ValueError(
                f"to_level ({self.to_level}) must be higher than from_level ({self.from_level})."
            )
        if not self.approver_id:
            raise ValueError("approver_id must not be empty.")
        if not self.reason:
            raise ValueError("reason must not be empty.")


@dataclass(frozen=True)
class TrustLevelEvent:
    """A recorded trust-level change event in the audit trail.

    Attributes:
        event_id:      Unique event identifier.
        agent_id:      Affected agent or tenant.
        old_level:     Trust level before the change.
        new_level:     Trust level after the change.
        reason:        Reason category for the change.
        detail:        Human-readable detail.
        approval_id:   Reference to the approval for promotions.
        timestamp:     UTC event timestamp.
        event_hash:    SHA-256 of all fields.
    """

    event_id: UUID
    agent_id: str
    old_level: TrustLevel
    new_level: TrustLevel
    reason: TrustLevelChangeReason
    detail: str
    approval_id: TrustLevelApprovalId | None
    timestamp: datetime
    event_hash: str

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


# ──────────────────────────────────────────────────────────────────────────────
# Kill plane (AD-038: independent out-of-band kill plane)
# ──────────────────────────────────────────────────────────────────────────────


class KillPlaneStatus(StrEnum):
    """Operational state of the kill plane."""

    ARMED = "armed"
    TRIGGERED = "triggered"
    DRAINING = "draining"
    HALTED = "halted"


class KillPlaneScope(StrEnum):
    """Scope of a kill-plane activation."""

    TENANT = "tenant"
    AGENT = "agent"
    PLATFORM = "platform"
    SYMBOL = "symbol"


@dataclass(frozen=True)
class KillPlaneCommandId:
    """Stable identity for a kill-plane command."""

    value: UUID

    @classmethod
    def generate(cls) -> KillPlaneCommandId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class KillPlaneCommand:
    """A command issued to the kill plane.

    Attributes:
        command_id:    Unique command identifier.
        scope:         Scope of effect (tenant, agent, platform, symbol).
        scope_value:   Specific value for scoped kills (e.g. tenant_id).
        issuer_id:     Identity of the issuer (human operator or watchdog).
        reason:        Human-readable reason for the kill.
        timestamp:     UTC timestamp.
        command_hash:  SHA-256 of all fields.
        out_of_band:   True when issued via out-of-band channel (main platform may be down).
    """

    command_id: KillPlaneCommandId
    scope: KillPlaneScope
    scope_value: str
    issuer_id: str
    reason: str
    timestamp: datetime
    command_hash: str
    out_of_band: bool = False

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if not self.issuer_id:
            raise ValueError("issuer_id must not be empty.")
        if not self.reason:
            raise ValueError("reason must not be empty.")


@dataclass
class KillPlaneResult:
    """Result of a kill-plane activation.

    Attributes:
        command_id:         The command that triggered this result.
        orders_cancelled:   Number of open orders cancelled.
        new_exposure_blocked: True when new exposure is blocked.
        status:             Resulting kill-plane status.
        detail:             Human-readable detail.
        timestamp:          UTC timestamp.
    """

    command_id: KillPlaneCommandId
    orders_cancelled: int
    new_exposure_blocked: bool
    status: KillPlaneStatus
    detail: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


# ──────────────────────────────────────────────────────────────────────────────
# Human-factors review
# ──────────────────────────────────────────────────────────────────────────────


class DangerousActionCategory(StrEnum):
    """Categories of actions requiring human-factors review."""

    TRUST_LEVEL_PROMOTION = "trust_level_promotion"
    KILL_PLANE_DEACTIVATION = "kill_plane_deactivation"
    LIVE_TRADING_ENABLE = "live_trading_enable"
    LARGE_ORDER = "large_order"
    EMERGENCY_POLICY_OVERRIDE = "emergency_policy_override"
    CREDENTIAL_ROTATION = "credential_rotation"
    SCHEMA_MIGRATION = "schema_migration"


@dataclass(frozen=True)
class HumanFactorsReviewId:
    """Stable identity for a human-factors review record."""

    value: UUID

    @classmethod
    def generate(cls) -> HumanFactorsReviewId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class HumanFactorsReview:
    """Record of a human-factors review for a dangerous action.

    Attributes:
        review_id:      Unique review identifier.
        category:       Action category reviewed.
        action_detail:  Human-readable description of the action.
        reviewer_id:    Identity of the reviewer.
        approved:       True if approved, False if rejected.
        notes:          Reviewer notes.
        timestamp:      UTC timestamp of the review decision.
        review_hash:    SHA-256 of all fields.
    """

    review_id: HumanFactorsReviewId
    category: DangerousActionCategory
    action_detail: str
    reviewer_id: str
    approved: bool
    notes: str
    timestamp: datetime
    review_hash: str

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


# ──────────────────────────────────────────────────────────────────────────────
# Operator cockpit — dashboard snapshot
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class OperatorCockpitSnapshot:
    """A point-in-time snapshot of the operator cockpit state.

    Attributes:
        snapshot_id:       Unique snapshot identifier.
        timestamp:         UTC snapshot timestamp.
        platform_mode:     Active operating mode (SIMULATION / PAPER / LIVE).
        kill_plane_status: Current kill-plane status.
        active_trust_levels: Map of agent_id → current TrustLevel.
        open_order_count:  Number of open orders across all tenants.
        pending_approvals: Number of pending trust-level approval requests.
        active_alerts:     List of active SLO or safety alerts (summary strings).
        compliance_flags:  Map of compliance item → True (ok) / False (issue).
    """

    snapshot_id: UUID
    timestamp: datetime
    platform_mode: str
    kill_plane_status: KillPlaneStatus
    active_trust_levels: dict[str, int]
    open_order_count: int
    pending_approvals: int
    active_alerts: list[str]
    compliance_flags: dict[str, bool]

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


# ──────────────────────────────────────────────────────────────────────────────
# Compliance package
# ──────────────────────────────────────────────────────────────────────────────


class ComplianceDocumentType(StrEnum):
    """Type of compliance document."""

    LEGAL_CLASSIFICATION_MEMO = "legal_classification_memo"
    DATA_INVENTORY = "data_inventory"
    DPIA = "dpia"
    MARKET_DATA_TERMS = "market_data_terms"
    PENETRATION_TEST_REPORT = "penetration_test_report"
    PLATFORM_EVALUATION_ADR = "platform_evaluation_adr"
    RUNBOOK = "runbook"
    TABLETOP_DRILL_RECORD = "tabletop_drill_record"


@dataclass(frozen=True)
class ComplianceDocumentId:
    """Stable identity for a compliance document."""

    value: UUID

    @classmethod
    def generate(cls) -> ComplianceDocumentId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ComplianceDocument:
    """A compliance package document record.

    Attributes:
        document_id:   Unique document identifier.
        doc_type:      Type of compliance document.
        title:         Document title.
        owner:         Document owner / responsible party.
        status:        Status (e.g. DRAFT, COMPLETE, OPEN).
        summary:       Human-readable summary of the document content.
        references:    List of referenced ADRs, regulations, or resources.
        timestamp:     UTC creation timestamp.
        doc_hash:      SHA-256 of title + owner + status + summary.
    """

    document_id: ComplianceDocumentId
    doc_type: ComplianceDocumentType
    title: str
    owner: str
    status: str
    summary: str
    references: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    doc_hash: str = ""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if not self.title:
            raise ValueError("title must not be empty.")
        if not self.owner:
            raise ValueError("owner must not be empty.")
        if self.doc_hash == "":
            self.doc_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "document_id": str(self.document_id),
                "doc_type": str(self.doc_type),
                "title": self.title,
                "owner": self.owner,
                "status": self.status,
                "summary": self.summary,
                "references": self.references,
                "timestamp": self.timestamp.isoformat(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class DataInventoryItem:
    """A single item in the data inventory (for DPIA / GDPR evidence).

    Attributes:
        item_id:         Unique item identifier.
        data_category:   Category of personal/sensitive data.
        description:     What data is stored or processed.
        storage_location: Where the data lives (e.g. PostgreSQL/users table).
        retention_days:  Retention period in days.
        lawful_basis:    Legal basis for processing (e.g. contract, consent).
        encrypted:       True if encrypted at rest.
        cross_tenant:    False — cross-tenant access is prohibited.
    """

    item_id: UUID
    data_category: str
    description: str
    storage_location: str
    retention_days: int
    lawful_basis: str
    encrypted: bool
    cross_tenant: bool = False

    def __post_init__(self) -> None:
        if self.cross_tenant:
            raise ValueError(
                "cross_tenant must be False — cross-tenant data access is prohibited (AD-007)."
            )
        if self.retention_days <= 0:
            raise ValueError("retention_days must be positive.")


@dataclass
class MarketDataTermsEntry:
    """An entry in the market-data terms register.

    Attributes:
        entry_id:       Unique entry identifier.
        provider:       Data provider name (e.g. Binance, CoinGecko).
        data_types:     List of data types covered (e.g. OHLCV, orderbook).
        permitted_uses: What the data may be used for under the terms.
        restrictions:   Prohibited uses or redistribution restrictions.
        license_url:    URL or reference to the license / ToS.
        reviewed_date:  Date the terms were last reviewed (UTC date string).
        reviewer_id:    Identity of the reviewer.
    """

    entry_id: UUID
    provider: str
    data_types: list[str]
    permitted_uses: list[str]
    restrictions: list[str]
    license_url: str
    reviewed_date: str
    reviewer_id: str

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("provider must not be empty.")
        if not self.reviewed_date:
            raise ValueError("reviewed_date must not be empty.")


# ──────────────────────────────────────────────────────────────────────────────
# Drill records (tabletop + live)
# ──────────────────────────────────────────────────────────────────────────────


class DrillType(StrEnum):
    """Type of operational drill."""

    TABLETOP = "tabletop"
    LIVE = "live"
    KILL_PLANE = "kill_plane"
    RUNBOOK = "runbook"


class DrillOutcome(StrEnum):
    """Outcome of an operational drill."""

    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class E9DrillRecordId:
    """Stable identity for an E9 drill record."""

    value: UUID

    @classmethod
    def generate(cls) -> E9DrillRecordId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class E9DrillRecord:
    """Record of a tabletop or live operational drill.

    Attributes:
        record_id:       Unique drill record identifier.
        drill_type:      Type of drill.
        title:           Short drill title.
        scenario:        What was tested (human-readable scenario description).
        participants:    List of participant identifiers.
        outcome:         Overall drill outcome.
        findings:        List of findings / gaps identified.
        action_items:    List of remediation action items.
        started_at:      UTC start timestamp.
        completed_at:    UTC completion timestamp (None if incomplete).
        record_hash:     SHA-256 of all fields.
    """

    record_id: E9DrillRecordId
    drill_type: DrillType
    title: str
    scenario: str
    participants: list[str]
    outcome: DrillOutcome
    findings: list[str]
    action_items: list[str]
    started_at: datetime
    completed_at: datetime | None
    record_hash: str = ""

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware (UTC).")
        if not self.title:
            raise ValueError("title must not be empty.")
        if self.record_hash == "":
            self.record_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "record_id": str(self.record_id),
                "drill_type": str(self.drill_type),
                "title": self.title,
                "scenario": self.scenario,
                "participants": self.participants,
                "outcome": str(self.outcome),
                "findings": self.findings,
                "action_items": self.action_items,
                "started_at": self.started_at.isoformat(),
                "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Owner review package
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class E9OwnerReviewPackage:
    """The complete E9 owner review package.

    Collecting all E9 deliverables in one structure for owner sign-off.
    Completing E9 does NOT authorize live trading.

    Attributes:
        package_id:            Unique package identifier.
        timestamp:             UTC generation timestamp.
        trust_level_events:    List of trust-level change events in the audit trail.
        kill_plane_drills:     Kill-plane drill records.
        compliance_documents:  All compliance package documents.
        data_inventory:        Data inventory items.
        market_data_terms:     Market-data terms register entries.
        human_factors_reviews: Human-factors review records for dangerous actions.
        operator_snapshots:    Operator cockpit snapshots captured during drills.
        drill_records:         All E9 drill records.
        live_trading_authorized: Always False — E9 does not authorize live trading.
        package_hash:          SHA-256 of all components (tamper evidence).
    """

    package_id: UUID
    timestamp: datetime
    trust_level_events: list[TrustLevelEvent]
    kill_plane_drills: list[KillPlaneResult]
    compliance_documents: list[ComplianceDocument]
    data_inventory: list[DataInventoryItem]
    market_data_terms: list[MarketDataTermsEntry]
    human_factors_reviews: list[HumanFactorsReview]
    operator_snapshots: list[OperatorCockpitSnapshot]
    drill_records: list[E9DrillRecord]
    live_trading_authorized: bool = False
    package_hash: str = ""

    def __post_init__(self) -> None:
        if self.live_trading_authorized:
            raise ValueError(
                "live_trading_authorized must be False — E9 does not authorize live trading."
            )
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.package_hash == "":
            self.package_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "package_id": str(self.package_id),
                "timestamp": self.timestamp.isoformat(),
                "trust_level_event_count": len(self.trust_level_events),
                "kill_plane_drill_count": len(self.kill_plane_drills),
                "compliance_document_count": len(self.compliance_documents),
                "data_inventory_count": len(self.data_inventory),
                "market_data_terms_count": len(self.market_data_terms),
                "human_factors_review_count": len(self.human_factors_reviews),
                "drill_record_count": len(self.drill_records),
                "live_trading_authorized": self.live_trading_authorized,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────────────────────


class TrustLevelError(Exception):
    """Base exception for trust-level errors."""


class TrustLevelPromotionDeniedError(TrustLevelError):
    """Raised when a promotion is denied (missing approval or invalid)."""


class TrustLevelDemotedError(TrustLevelError):
    """Raised to signal that an agent has been automatically demoted."""


class KillPlaneError(Exception):
    """Base exception for kill-plane errors."""


class KillPlaneAlreadyTriggeredError(KillPlaneError):
    """Raised when the kill plane has already been triggered."""


class KillPlaneNotArmedError(KillPlaneError):
    """Raised when the kill plane is not in ARMED state."""


# ──────────────────────────────────────────────────────────────────────────────
# Utility: build an approval hash
# ──────────────────────────────────────────────────────────────────────────────


def compute_approval_hash(approval: dict[str, Any]) -> str:
    """Return the SHA-256 hash of a serialised approval dict."""
    return hashlib.sha256(json.dumps(approval, sort_keys=True).encode()).hexdigest()


def compute_event_hash(event: dict[str, Any]) -> str:
    """Return the SHA-256 hash of a serialised event dict."""
    return hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
