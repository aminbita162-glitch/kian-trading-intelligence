"""Approved locked-idea contracts for Kian Trading Intelligence.

Per DIRECTIV.txt V1.4 Section 01.8 — all 10 ideas confirmed by the owner
for implementation as additive, non-breaking enhancements.

Each idea preserves all existing invariants and safety controls:
- live_trading_authorized remains always False (Section 00.3).
- Risk Kernel, kill plane and audit trail are never weakened (Section 03).
- No cross-tenant data access (AD-007).

The 10 approved locked ideas:
 1. LLM metering + Token Budget Governor
 2. Structured digest + delta context
 3. Short-lived capability credentials + Dual-LLM quarantine
 4. Event-driven invocation
 5. Decision Replay + uncertainty dossier
 6. Dual Control (WebAuthn)
 7. Shadow-Live + point-in-time Feature Store
 8. Schema-First Bus + Eval-Driven Development
 9. Live Unit Economics + per-tenant kill/restart
10. Continuous chaos for exchange scenarios + operator cockpit

These contracts are leaf-level — they must NOT import from services or
simulation (import-linter contracts-is-leaf).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

# ═══════════════════════════════════════════════════════════════════════════════
# Idea 1 — LLM metering + Token Budget Governor
# ═══════════════════════════════════════════════════════════════════════════════
#
# Extends the existing LLM gateway (contracts.llm_gateway) with a governor
# that enforces token-budget policy across all tenants and prevents any
# single tenant from consuming a disproportionate share of the shared pool.


@dataclass(frozen=True)
class MeteringRecordId:
    """Stable identity for a metering record."""

    value: UUID

    @classmethod
    def generate(cls) -> MeteringRecordId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


class MeteringDimension(StrEnum):
    """Dimensions tracked by the token-budget governor."""

    LLM_TOKENS = "llm_tokens"
    LLM_REQUESTS = "llm_requests"
    MARKET_DATA_REQUESTS = "market_data_requests"
    COMPUTE_SECONDS = "compute_seconds"


@dataclass(frozen=True)
class MeteringRecord:
    """A single metering event for a tenant.

    Attributes:
        record_id:   Unique record identifier.
        tenant_id:   Tenant scope.
        dimension:   What was metered (tokens, requests, etc.).
        amount:      Quantity consumed.
        timestamp:   UTC consumption timestamp.
        metadata:    Additional key-value context (e.g. request type).
    """

    record_id: MeteringRecordId
    tenant_id: str
    dimension: MeteringDimension
    amount: int
    timestamp: datetime
    metadata: dict[str, str] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.amount < 0:
            raise ValueError("amount must be non-negative.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass(frozen=True)
class TokenBudgetGovernorConfig:
    """Configuration for the token-budget governor.

    Attributes:
        global_daily_token_limit: Total tokens across all tenants per day.
        per_tenant_token_limit:   Maximum tokens a single tenant can consume per day.
        per_tenant_request_limit: Maximum LLM requests a single tenant can make per day.
        burst_allowance:          Extra tokens allowed in short bursts above steady-state.
    """

    global_daily_token_limit: int = 100000
    per_tenant_token_limit: int = 10000
    per_tenant_request_limit: int = 100
    burst_allowance: int = 2000

    def __post_init__(self) -> None:
        MIN_LIMIT = 1
        if self.global_daily_token_limit < MIN_LIMIT:
            raise ValueError("global_daily_token_limit must be >= 1.")
        if self.per_tenant_token_limit < MIN_LIMIT:
            raise ValueError("per_tenant_token_limit must be >= 1.")
        if self.per_tenant_request_limit < MIN_LIMIT:
            raise ValueError("per_tenant_request_limit must be >= 1.")
        if self.burst_allowance < 0:
            raise ValueError("burst_allowance must be non-negative.")
        if self.per_tenant_token_limit > self.global_daily_token_limit:
            raise ValueError("per_tenant_token_limit must not exceed global_daily_token_limit.")


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 2 — Structured digest + delta context
# ═══════════════════════════════════════════════════════════════════════════════
#
# Provides a structured, hash-chained digest of platform state changes with
# delta context so the operator can see what changed between snapshots
# without replaying the entire state.


@dataclass(frozen=True)
class DigestId:
    """Stable identity for a structured digest."""

    value: UUID

    @classmethod
    def generate(cls) -> DigestId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


class DigestScope(StrEnum):
    """Scope of a structured digest."""

    PLATFORM = "platform"
    TENANT = "tenant"
    AGENT = "agent"


@dataclass(frozen=True)
class DeltaEntry:
    """A single delta entry within a structured digest.

    Attributes:
        field_path: Dotted path to the changed field (e.g. "risk.exposure_btc").
        old_value: Previous value (string representation).
        new_value: Current value (string representation).
        change_type: Type of change (add, remove, update).
    """

    field_path: str
    old_value: str
    new_value: str
    change_type: str

    def __post_init__(self) -> None:
        if not self.field_path:
            raise ValueError("field_path must not be empty.")
        if self.change_type not in ("add", "remove", "update"):
            raise ValueError("change_type must be 'add', 'remove', or 'update'.")


@dataclass(frozen=True)
class StructuredDigest:
    """A hash-chained structured digest of platform state.

    Attributes:
        digest_id:      Unique digest identifier.
        scope:          Digest scope (platform, tenant, agent).
        scope_value:    Specific value for the scope (e.g. tenant_id).
        timestamp:      UTC digest timestamp.
        state_snapshot: Key-value map of the current state at digest time.
        deltas:         Changes from the previous digest (may be empty for the first).
        previous_hash:  Hash of the previous digest (empty for genesis).
        digest_hash:    SHA-256 of all fields.
    """

    digest_id: DigestId
    scope: DigestScope
    scope_value: str
    timestamp: datetime
    state_snapshot: dict[str, str] = field(default_factory=dict, compare=False)
    deltas: list[DeltaEntry] = field(default_factory=list, compare=False)
    previous_hash: str = ""
    digest_hash: str = ""

    def __post_init__(self) -> None:
        if not self.scope_value:
            raise ValueError("scope_value must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.digest_hash == "":
            object.__setattr__(self, "digest_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "digest_id": str(self.digest_id),
                "scope": str(self.scope),
                "scope_value": self.scope_value,
                "timestamp": self.timestamp.isoformat(),
                "state_snapshot": self.state_snapshot,
                "deltas": [
                    {
                        "field_path": d.field_path,
                        "old_value": d.old_value,
                        "new_value": d.new_value,
                        "change_type": d.change_type,
                    }
                    for d in self.deltas
                ],
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 3 — Short-lived capability credentials + Dual-LLM quarantine
# ═══════════════════════════════════════════════════════════════════════════════
#
# Short-lived, scoped capability tokens that grant time-bounded access to
# specific platform capabilities. Dual-LLM quarantine ensures that LLM
# outputs from two independent models must agree before being used for
# sensitive operations.


class CapabilityScope(StrEnum):
    """Scopes for short-lived capability credentials."""

    MARKET_DATA_READ = "market_data_read"
    STRATEGY_EVALUATE = "strategy_evaluate"
    RISK_SUMMARIZE = "risk_summarize"
    MINING_PROFITABILITY = "mining_profitability"


@dataclass(frozen=True)
class CapabilityCredentialId:
    """Stable identity for a capability credential."""

    value: UUID

    @classmethod
    def generate(cls) -> CapabilityCredentialId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class CapabilityCredential:
    """A short-lived, scoped capability credential.

    Attributes:
        credential_id: Unique credential identifier.
        tenant_id:    Tenant scope.
        scope:        Capability scope granted.
        issued_at:    UTC issue timestamp.
        expires_at:   UTC expiry timestamp (must be after issued_at).
        secret_hash:  SHA-256 hash of the credential secret (not the secret itself).
    """

    credential_id: CapabilityCredentialId
    tenant_id: str
    scope: CapabilityScope
    issued_at: datetime
    expires_at: datetime
    secret_hash: str

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.issued_at.tzinfo is None:
            raise ValueError("issued_at must be timezone-aware (UTC).")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware (UTC).")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at.")
        if not self.secret_hash:
            raise ValueError("secret_hash must not be empty.")

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at

    @property
    def ttl_seconds(self) -> int:
        remaining = self.expires_at - datetime.now(UTC)
        return max(0, int(remaining.total_seconds()))


DEFAULT_CAPABILITY_TTL_SECONDS = 300  # 5 minutes


@dataclass(frozen=True)
class DualLLMQuarantineResult:
    """Result of a dual-LLM quarantine check.

    When two independent LLMs are queried for the same prompt, the
    quarantine ensures their outputs agree before the result is used.

    Attributes:
        result_id:     Unique result identifier.
        prompt_hash:   SHA-256 of the prompt (not the prompt itself).
        model_a_output: Output from model A.
        model_b_output: Output from model B.
        agreed:        True if both outputs agree (exact or semantic match).
        timestamp:     UTC quarantine check timestamp.
    """

    result_id: UUID
    prompt_hash: str
    model_a_output: str
    model_b_output: str
    agreed: bool
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if not self.prompt_hash:
            raise ValueError("prompt_hash must not be empty.")


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 4 — Event-driven invocation
# ═══════════════════════════════════════════════════════════════════════════════
#
# An event-driven invocation layer that routes domain events to registered
# handlers. Events carry a typed payload and are delivered at-least-once
# (in production the transport would be Redis Streams per Section 01.2).


class EventInvocationType(StrEnum):
    """Types of events that can trigger agent invocations."""

    MARKET_DATA_UPDATE = "market_data_update"
    RISK_THRESHOLD_BREACH = "risk_threshold_breach"
    ORDER_FILL = "order_fill"
    STRATEGY_SIGNAL = "strategy_signal"
    KILL_PLANE_TRIGGERED = "kill_plane_triggered"
    SCHEDULED_TICK = "scheduled_tick"


@dataclass(frozen=True)
class EventEnvelopeId:
    """Stable identity for an event envelope."""

    value: UUID

    @classmethod
    def generate(cls) -> EventEnvelopeId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class EventEnvelope:
    """A typed event envelope for event-driven invocation.

    Attributes:
        envelope_id: Unique envelope identifier.
        event_type:  Type of event.
        tenant_id:   Tenant scope (may be "platform" for platform-wide events).
        payload:     Event payload (key-value, compare=False for hashing).
        timestamp:   UTC event timestamp.
        event_hash:  SHA-256 hash of the event for dedup/integrity.
    """

    envelope_id: EventEnvelopeId
    event_type: EventInvocationType
    tenant_id: str
    payload: dict[str, Any] = field(default_factory=dict, compare=False)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_hash: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.event_hash == "":
            object.__setattr__(self, "event_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        payload_data = json.dumps(
            {
                "envelope_id": str(self.envelope_id),
                "event_type": str(self.event_type),
                "tenant_id": self.tenant_id,
                "payload": self.payload,
                "timestamp": self.timestamp.isoformat(),
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload_data.encode()).hexdigest()


@dataclass(frozen=True)
class InvocationResult:
    """Result of an event-driven agent invocation.

    Attributes:
        envelope_id:   The event that triggered this invocation.
        handler_name:  Name of the handler that processed the event.
        success:       True if the handler completed successfully.
        detail:        Human-readable result detail.
        timestamp:     UTC completion timestamp.
    """

    envelope_id: EventEnvelopeId
    handler_name: str
    success: bool
    detail: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if not self.handler_name:
            raise ValueError("handler_name must not be empty.")


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 5 — Decision Replay + uncertainty dossier
# ═══════════════════════════════════════════════════════════════════════════════
#
# Records the full context of each agent decision so it can be replayed
# deterministically. An uncertainty dossier tracks confidence intervals,
# alternative considered, and risk of the decision.


@dataclass(frozen=True)
class DecisionReplayId:
    """Stable identity for a decision replay record."""

    value: UUID

    @classmethod
    def generate(cls) -> DecisionReplayId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


class DecisionType(StrEnum):
    """Types of agent decisions that are replayable."""

    ORDER_SUBMISSION = "order_submission"
    STRATEGY_SELECTION = "strategy_selection"
    RISK_ASSESSMENT = "risk_assessment"
    MINING_ALLOCATION = "mining_allocation"


@dataclass(frozen=True)
class UncertaintyDossier:
    """An uncertainty dossier for a decision.

    Attributes:
        confidence_score: 0.0–1.0 confidence in the decision.
        alternatives:      List of alternative actions considered.
        key_assumptions:  Key assumptions made.
        risk_factors:     Risk factors identified.
        max_regret:       Maximum regret if the decision is wrong (estimated).
    """

    confidence_score: float
    alternatives: list[str] = field(default_factory=list, compare=False)
    key_assumptions: list[str] = field(default_factory=list, compare=False)
    risk_factors: list[str] = field(default_factory=list, compare=False)
    max_regret: str = "unknown"

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0.")


@dataclass(frozen=True)
class DecisionReplayRecord:
    """A replayable record of an agent decision.

    Attributes:
        replay_id:        Unique replay identifier.
        decision_type:    Type of decision.
        tenant_id:        Tenant scope.
        agent_id:         Agent that made the decision.
        context_hash:     SHA-256 of the input context (for replay matching).
        action_taken:     The action that was decided.
        dossier:          Uncertainty dossier for this decision.
        timestamp:        UTC decision timestamp.
        record_hash:      SHA-256 of all fields.
    """

    replay_id: DecisionReplayId
    decision_type: DecisionType
    tenant_id: str
    agent_id: str
    context_hash: str
    action_taken: str
    dossier: UncertaintyDossier
    timestamp: datetime
    record_hash: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if not self.agent_id:
            raise ValueError("agent_id must not be empty.")
        if not self.context_hash:
            raise ValueError("context_hash must not be empty.")
        if not self.action_taken:
            raise ValueError("action_taken must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.record_hash == "":
            object.__setattr__(self, "record_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "replay_id": str(self.replay_id),
                "decision_type": str(self.decision_type),
                "tenant_id": self.tenant_id,
                "agent_id": self.agent_id,
                "context_hash": self.context_hash,
                "action_taken": self.action_taken,
                "confidence_score": self.dossier.confidence_score,
                "timestamp": self.timestamp.isoformat(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 6 — Dual Control (WebAuthn)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Dual-control approval for dangerous actions using WebAuthn-compatible
# hardware keys. Requires two distinct approvers for high-risk operations.


class DualControlAction(StrEnum):
    """Actions that require dual-control approval."""

    LIVE_TRADING_ENABLE = "live_trading_enable"
    KILL_PLANE_DEACTIVATION = "kill_plane_deactivation"
    LARGE_ORDER_APPROVAL = "large_order_approval"
    CREDENTIAL_ROTATION = "credential_rotation"
    TRUST_LEVEL_PROMOTION = "trust_level_promotion"


class WebAuthnCredentialType(StrEnum):
    """WebAuthn credential transport types."""

    PLATFORM = "platform"  # built-in (Touch ID, Windows Hello)
    CROSS_PLATFORM = "cross_platform"  # hardware security key (YubiKey)


@dataclass(frozen=True)
class DualControlRequestId:
    """Stable identity for a dual-control request."""

    value: UUID

    @classmethod
    def generate(cls) -> DualControlRequestId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class WebAuthnAssertion:
    """A single WebAuthn assertion from one approver.

    Attributes:
        credential_type:  Type of WebAuthn credential.
        credential_id:    ID of the credential used.
        authenticator_data: Base64-encoded authenticator data.
        client_data_hash:  SHA-256 of the client data JSON.
        signature:        Base64-encoded signature.
        approver_id:      Identity of the approver.
        timestamp:        UTC assertion timestamp.
    """

    credential_type: WebAuthnCredentialType
    credential_id: str
    authenticator_data: str
    client_data_hash: str
    signature: str
    approver_id: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.credential_id:
            raise ValueError("credential_id must not be empty.")
        if not self.approver_id:
            raise ValueError("approver_id must not be empty.")
        if not self.signature:
            raise ValueError("signature must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass(frozen=True)
class DualControlRequest:
    """A dual-control approval request for a dangerous action.

    Requires two distinct WebAuthn assertions from two different approvers.

    Attributes:
        request_id:   Unique request identifier.
        action:       Action that requires dual control.
        tenant_id:    Tenant scope.
        initiated_by: Who requested the action.
        detail:       Human-readable description of the action.
        assertions:   List of WebAuthn assertions (must have >= 2 for approval).
        timestamp:    UTC request timestamp.
        approved:     True if both assertions are present and valid.
    """

    request_id: DualControlRequestId
    action: DualControlAction
    tenant_id: str
    initiated_by: str
    detail: str
    assertions: list[WebAuthnAssertion] = field(default_factory=list, compare=False)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    approved: bool = False

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if not self.initiated_by:
            raise ValueError("initiated_by must not be empty.")
        if not self.detail:
            raise ValueError("detail must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")

    @property
    def is_approved(self) -> bool:
        """True when two distinct approvers have provided valid assertions."""
        MIN_ASSERTIONS = 2
        if len(self.assertions) < MIN_ASSERTIONS:
            return False
        approver_ids = {a.approver_id for a in self.assertions}
        return len(approver_ids) >= MIN_ASSERTIONS


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 7 — Shadow-Live + point-in-time Feature Store
# ═══════════════════════════════════════════════════════════════════════════════
#
# A shadow-live mode that runs strategies in parallel with live data without
# executing real orders, plus a point-in-time feature store that snapshots
# features as they were at a specific moment for reproducible backtesting.


class ShadowLiveMode(StrEnum):
    """Shadow-live operational modes."""

    SHADOW = "shadow"  # observe live data, no execution
    DISABLED = "disabled"


@dataclass(frozen=True)
class FeatureStoreEntryId:
    """Stable identity for a feature store entry."""

    value: UUID

    @classmethod
    def generate(cls) -> FeatureStoreEntryId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class FeatureStoreEntry:
    """A point-in-time feature store entry.

    Attributes:
        entry_id:    Unique entry identifier.
        feature_set: Name of the feature set (e.g. "btc_1h_technicals").
        as_of:      The point-in-time timestamp (features as they were at this moment).
        features:   Feature key-value map (compare=False for hashing).
        entry_hash: SHA-256 of the feature values + timestamp.
    """

    entry_id: FeatureStoreEntryId
    feature_set: str
    as_of: datetime
    features: dict[str, str] = field(default_factory=dict, compare=False)
    entry_hash: str = ""

    def __post_init__(self) -> None:
        if not self.feature_set:
            raise ValueError("feature_set must not be empty.")
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware (UTC).")
        if self.entry_hash == "":
            object.__setattr__(self, "entry_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "entry_id": str(self.entry_id),
                "feature_set": self.feature_set,
                "as_of": self.as_of.isoformat(),
                "features": self.features,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class ShadowLiveResult:
    """Result of a shadow-live strategy run.

    Attributes:
        run_id:        Unique run identifier.
        strategy_id:   Strategy that was shadow-run.
        feature_entry_id: Feature store entry used as input.
        proposed_action: What the strategy would have done.
        executed:      Always False — shadow mode never executes.
        timestamp:     UTC run timestamp.
    """

    run_id: UUID
    strategy_id: str
    feature_entry_id: FeatureStoreEntryId
    proposed_action: str
    executed: bool
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.executed:
            raise ValueError("executed must be False — shadow mode never executes real orders.")


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 8 — Schema-First Bus + Eval-Driven Development
# ═══════════════════════════════════════════════════════════════════════════════
#
# Schema-first event bus: all events must conform to a registered JSON
# schema before they can be published. Eval-driven development requires
# that every schema change passes an evaluation gate.


@dataclass(frozen=True)
class SchemaBusTopicId:
    """Stable identity for a schema-bus topic."""

    value: UUID

    @classmethod
    def generate(cls) -> SchemaBusTopicId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SchemaBusTopic:
    """A schema-first bus topic with a JSON schema.

    Attributes:
        topic_id:    Unique topic identifier.
        name:        Topic name (e.g. "market_data.ticker").
        schema_json: JSON schema that all messages on this topic must satisfy.
        version:     Schema version (monotonically increasing).
        eval_passed: True if the evaluation gate passed for this schema version.
    """

    topic_id: SchemaBusTopicId
    name: str
    schema_json: dict[str, Any] = field(default_factory=dict, compare=False)
    version: int = 1
    eval_passed: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty.")
        if self.version < 1:
            raise ValueError("version must be >= 1.")


@dataclass(frozen=True)
class EvalGateResult:
    """Result of an evaluation gate run for a schema change.

    Attributes:
        gate_id:      Unique gate run identifier.
        topic_name:   Topic being evaluated.
        schema_version: Schema version evaluated.
        test_count:   Number of tests run.
        passed:        True if all tests passed.
        timestamp:    UTC gate run timestamp.
    """

    gate_id: UUID
    topic_name: str
    schema_version: int
    test_count: int
    passed: bool
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.topic_name:
            raise ValueError("topic_name must not be empty.")
        if self.test_count < 0:
            raise ValueError("test_count must be non-negative.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 9 — Live Unit Economics + per-tenant kill/restart
# ═══════════════════════════════════════════════════════════════════════════════
#
# Extends the existing UnitEconomicsService with per-tenant kill and
# restart capabilities. The kill plane (contracts.autonomy) already
# supports TENANT-scoped kills; this adds a restart workflow.


class TenantLifecycleAction(StrEnum):
    """Per-tenant lifecycle actions."""

    KILL = "kill"
    RESTART = "restart"
    PAUSE = "pause"
    RESUME = "resume"


@dataclass(frozen=True)
class TenantLifecycleRequestId:
    """Stable identity for a tenant lifecycle request."""

    value: UUID

    @classmethod
    def generate(cls) -> TenantLifecycleRequestId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class TenantLifecycleRequest:
    """A per-tenant kill or restart request.

    Attributes:
        request_id:  Unique request identifier.
        tenant_id:   Tenant to act on.
        action:      Lifecycle action (kill, restart, pause, resume).
        issuer_id:   Who issued the request (operator or automated system).
        reason:      Human-readable reason.
        timestamp:   UTC request timestamp.
        approved:    True if the request was approved by human operator.
        executed:     True if the request was executed.
    """

    request_id: TenantLifecycleRequestId
    tenant_id: str
    action: TenantLifecycleAction
    issuer_id: str
    reason: str
    timestamp: datetime
    approved: bool = False
    executed: bool = False

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if not self.issuer_id:
            raise ValueError("issuer_id must not be empty.")
        if not self.reason:
            raise ValueError("reason must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass(frozen=True)
class TenantEconomicsSnapshot:
    """Per-tenant live economics snapshot.

    Attributes:
        snapshot_id:     Unique snapshot identifier.
        tenant_id:       Tenant scope.
        timestamp:       UTC snapshot timestamp.
        mrr_usd:         Monthly recurring revenue for this tenant.
        orders_today:    Number of orders today.
        tokens_used_today: LLM tokens used today.
        is_paused:       True if the tenant is paused/killed.
        snapshot_hash:   SHA-256 of all fields.
    """

    snapshot_id: UUID
    tenant_id: str
    timestamp: datetime
    mrr_usd: str
    orders_today: int
    tokens_used_today: int
    is_paused: bool
    snapshot_hash: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.snapshot_hash == "":
            object.__setattr__(self, "snapshot_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "snapshot_id": str(self.snapshot_id),
                "tenant_id": self.tenant_id,
                "timestamp": self.timestamp.isoformat(),
                "mrr_usd": self.mrr_usd,
                "orders_today": self.orders_today,
                "tokens_used_today": self.tokens_used_today,
                "is_paused": self.is_paused,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# Idea 10 — Continuous chaos for exchange scenarios + operator cockpit
# ═══════════════════════════════════════════════════════════════════════════════
#
# Continuous chaos engineering for exchange adapter scenarios. Runs
# fault-injection drills on a schedule and reports results to the
# operator cockpit (contracts.autonomy.OperatorCockpitSnapshot).


class ChaosScenarioType(StrEnum):
    """Types of chaos scenarios for exchange adapters."""

    LATENCY_SPIKE = "latency_spike"
    PARTIAL_FILL_STORM = "partial_fill_storm"
    ORDER_REJECTION = "order_rejection"
    CONNECTION_DROP = "connection_drop"
    RATE_LIMIT_HIT = "rate_limit_hit"
    STALE_ORDERBOOK = "stale_orderbook"
    DUPLICATE_ORDER = "duplicate_order"
    BALANCE_MISMATCH = "balance_mismatch"


@dataclass(frozen=True)
class ChaosScenarioId:
    """Stable identity for a chaos scenario."""

    value: UUID

    @classmethod
    def generate(cls) -> ChaosScenarioId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ChaosScenarioResult:
    """Result of running a single chaos scenario.

    Attributes:
        result_id:     Unique result identifier.
        scenario_id:   The scenario that was run.
        scenario_type: Type of chaos scenario.
        exchange:       Exchange adapter tested (e.g. "kraken").
        passed:         True if the system handled the fault correctly.
        duration_seconds: How long the scenario ran.
        findings:       List of findings (empty if passed).
        timestamp:      UTC scenario completion timestamp.
    """

    result_id: UUID
    scenario_id: ChaosScenarioId
    scenario_type: ChaosScenarioType
    exchange: str
    passed: bool
    duration_seconds: float
    findings: list[str] = field(default_factory=list, compare=False)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.exchange:
            raise ValueError("exchange must not be empty.")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass(frozen=True)
class ChaosDrillReport:
    """A report from a continuous chaos drill run.

    Attributes:
        report_id:      Unique report identifier.
        drill_name:      Name of the drill.
        scenarios_run:   Number of scenarios executed.
        scenarios_passed: Number of scenarios that passed.
        results:         Individual scenario results.
        started_at:      UTC start timestamp.
        completed_at:    UTC completion timestamp.
        report_hash:     SHA-256 of all fields.
    """

    report_id: UUID
    drill_name: str
    scenarios_run: int
    scenarios_passed: int
    started_at: datetime
    completed_at: datetime
    results: list[ChaosScenarioResult] = field(default_factory=list, compare=False)
    report_hash: str = ""

    def __post_init__(self) -> None:
        if not self.drill_name:
            raise ValueError("drill_name must not be empty.")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware (UTC).")
        if self.scenarios_run < 0:
            raise ValueError("scenarios_run must be non-negative.")
        if self.scenarios_passed < 0 or self.scenarios_passed > self.scenarios_run:
            raise ValueError("scenarios_passed must be 0..scenarios_run.")
        if self.report_hash == "":
            object.__setattr__(self, "report_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "report_id": str(self.report_id),
                "drill_name": self.drill_name,
                "scenarios_run": self.scenarios_run,
                "scenarios_passed": self.scenarios_passed,
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @property
    def all_passed(self) -> bool:
        return self.scenarios_passed == self.scenarios_run


# ──────────────────────────────────────────────────────────────────────────────
# Safety invariant: the 10 locked ideas never authorize live trading
# ──────────────────────────────────────────────────────────────────────────────

#: Safety constant — all locked-idea features must preserve this.
LOCKED_IDEAS_LIVE_TRADING_AUTHORIZED: bool = False

#: The 10 approved locked ideas from DIRECTIV.txt Section 01.8.
APPROVED_LOCKED_IDEAS: tuple[str, ...] = (
    "LLM metering + Token Budget Governor",
    "Structured digest + delta context",
    "Short-lived capability credentials + Dual-LLM quarantine",
    "Event-driven invocation",
    "Decision Replay + uncertainty dossier",
    "Dual Control (WebAuthn)",
    "Shadow-Live + point-in-time Feature Store",
    "Schema-First Bus + Eval-Driven Development",
    "Live Unit Economics + per-tenant kill/restart",
    "Continuous chaos for exchange scenarios + operator cockpit",
)


def compute_capability_secret_hash(secret: str) -> str:
    """Compute a SHA-256 hash of a capability credential secret.

    The hash is what is stored — the raw secret is never persisted.
    """
    if not secret:
        raise ValueError("secret must not be empty.")
    return hashlib.sha256(secret.encode()).hexdigest()


def compute_prompt_hash(prompt: str) -> str:
    """Compute a SHA-256 hash of an LLM prompt for dual-LLM quarantine."""
    if not prompt:
        raise ValueError("prompt must not be empty.")
    return hashlib.sha256(prompt.encode()).hexdigest()


def compute_context_hash(context: dict[str, Any]) -> str:
    """Compute a SHA-256 hash of a decision context for replay matching."""
    payload = json.dumps(context, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def hmac_assertion(assertion: WebAuthnAssertion, key: bytes) -> str:
    """Compute an HMAC-SHA256 over a WebAuthn assertion for integrity."""
    msg = (
        f"{assertion.credential_id}|"
        f"{assertion.client_data_hash}|"
        f"{assertion.signature}|"
        f"{assertion.approver_id}|"
        f"{assertion.timestamp.isoformat()}"
    ).encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()
