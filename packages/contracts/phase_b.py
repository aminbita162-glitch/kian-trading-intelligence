"""Phase B contracts — operational locked ideas.

Per DIRECTIV.txt V1.4 Phase B: three ideas fully implemented with
real service code, integration tests, and runtime connection.

1. Token Budget Governor + accurate metering (LLM tokens, compute, orders)
   with per-tenant budgets and graceful degradation.
2. Decision Replay + uncertainty dossier for the order path.
3. Schema-First Bus: contract validation of all event schemas.

These contracts extend the existing locked-ideas contracts
(contracts.locked_ideas) with production-grade types needed for
runtime integration. All existing safety invariants are preserved:
- live_trading_authorized remains always False (Section 00.3).
- Risk Kernel, kill plane and audit trail are never weakened.
- No cross-tenant data access (AD-007).

Leaf-level — must NOT import from services or simulation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from contracts.locked_ideas import UncertaintyDossier

# ═══════════════════════════════════════════════════════════════════════════════
# Item 1 — Token Budget Governor + accurate metering
# ═══════════════════════════════════════════════════════════════════════════════
#
# Extends the existing TokenBudgetGovernor (contracts.locked_ideas) with:
# - Multi-dimension metering (LLM tokens, compute seconds, orders)
# - Per-tenant budgets for each dimension
# - Graceful degradation: when a budget is exceeded, the system degrades
#   rather than hard-failing


class DegradationLevel(StrEnum):
    """Degradation level when a budget is exceeded."""

    NONE = "none"  # No degradation — budget is fine
    LIGHT = "light"  # Light degradation — reduce token allocation
    MODERATE = "moderate"  # Moderate degradation — skip non-critical processing
    SEVERE = "severe"  # Severe degradation — queue orders, use cached responses


@dataclass(frozen=True)
class TenantBudgetConfig:
    """Per-tenant budget configuration for all metering dimensions.

    Attributes:
        tenant_id: Tenant scope.
        llm_token_daily_limit: Maximum LLM tokens per day.
        compute_seconds_daily_limit: Maximum compute seconds per day.
        orders_daily_limit: Maximum orders per day.
        llm_token_burst: Burst allowance above steady-state.
    """

    tenant_id: str
    llm_token_daily_limit: int = 10000
    compute_seconds_daily_limit: int = 3600
    orders_daily_limit: int = 100
    llm_token_burst: int = 2000

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        MIN_LIMIT = 1
        if self.llm_token_daily_limit < MIN_LIMIT:
            raise ValueError("llm_token_daily_limit must be >= 1.")
        if self.compute_seconds_daily_limit < MIN_LIMIT:
            raise ValueError("compute_seconds_daily_limit must be >= 1.")
        if self.orders_daily_limit < MIN_LIMIT:
            raise ValueError("orders_daily_limit must be >= 1.")
        if self.llm_token_burst < 0:
            raise ValueError("llm_token_burst must be non-negative.")


@dataclass(frozen=True)
class MeteringSnapshot:
    """A snapshot of metering usage for a tenant.

    Captures the current usage across all dimensions at a point in time.
    Used for reporting and degradation decisions.

    Attributes:
        snapshot_id: Unique snapshot identifier.
        tenant_id: Tenant scope.
        llm_tokens_used: LLM tokens consumed today.
        compute_seconds_used: Compute seconds consumed today.
        orders_today: Number of orders submitted today.
        llm_requests_today: Number of LLM requests today.
        degradation_level: Current degradation level.
        timestamp: UTC snapshot timestamp.
    """

    snapshot_id: UUID
    tenant_id: str
    llm_tokens_used: int
    compute_seconds_used: int
    orders_today: int
    llm_requests_today: int
    degradation_level: DegradationLevel
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.llm_tokens_used < 0:
            raise ValueError("llm_tokens_used must be non-negative.")
        if self.compute_seconds_used < 0:
            raise ValueError("compute_seconds_used must be non-negative.")
        if self.orders_today < 0:
            raise ValueError("orders_today must be non-negative.")
        if self.llm_requests_today < 0:
            raise ValueError("llm_requests_today must be non-negative.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass(frozen=True)
class MeteringResult:
    """Result of a metering operation.

    Indicates whether the consumption was accepted within budget or
    whether degradation was applied.

    Attributes:
        accepted: True if the consumption was accepted within budget.
        degraded: True if graceful degradation was applied.
        degradation_level: The degradation level (NONE if accepted).
        remaining_llm_tokens: Remaining LLM tokens for the tenant.
        remaining_orders: Remaining orders for the tenant.
        detail: Human-readable detail.
    """

    accepted: bool
    degraded: bool
    degradation_level: DegradationLevel
    remaining_llm_tokens: int
    remaining_orders: int
    detail: str

    def __post_init__(self) -> None:
        if self.remaining_llm_tokens < 0:
            raise ValueError("remaining_llm_tokens must be non-negative.")
        if self.remaining_orders < 0:
            raise ValueError("remaining_orders must be non-negative.")


# ═══════════════════════════════════════════════════════════════════════════════
# Item 2 — Decision Replay + uncertainty dossier for the order path
# ═══════════════════════════════════════════════════════════════════════════════
#
# Extends the existing DecisionReplayRecord (contracts.locked_ideas) with
# order-path-specific types that capture the full decision context:
# - Market state at decision time
# - Risk assessment result
# - Execution outcome
# - Uncertainty dossier with confidence, alternatives, risk factors


@dataclass(frozen=True)
class OrderDecisionContext:
    """The full context of an order-path decision.

    Captures the market state and order parameters that were present
    when the decision was made, enabling deterministic replay.

    Attributes:
        tenant_id: Tenant scope.
        symbol: Trading symbol (e.g. "BTC/USDT").
        side: Order side ("buy" or "sell").
        quantity: Order quantity (string for exact decimal).
        current_price: Market price at decision time.
        risk_authorized: Whether the risk kernel authorized the order.
        risk_reason: Risk kernel reason (if denied).
        execution_state: Resulting execution state.
    """

    tenant_id: str
    symbol: str
    side: str
    quantity: str
    current_price: str
    risk_authorized: bool
    risk_reason: str
    execution_state: str

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if not self.symbol:
            raise ValueError("symbol must not be empty.")
        if self.side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'.")
        if not self.quantity:
            raise ValueError("quantity must not be empty.")
        if not self.current_price:
            raise ValueError("current_price must not be empty.")

    def to_hashable(self) -> dict[str, str]:
        """Return a JSON-serializable dict for context hashing."""
        return {
            "tenant_id": self.tenant_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "current_price": self.current_price,
            "risk_authorized": str(self.risk_authorized),
            "execution_state": self.execution_state,
        }


@dataclass(frozen=True)
class OrderDecisionRecord:
    """A replayable record of an order-path decision.

    Combines the decision context, action taken, and uncertainty dossier
    into a single auditable record.

    Attributes:
        record_id: Unique record identifier.
        context: The full order decision context.
        action_taken: The action that was decided.
        dossier: Uncertainty dossier for this decision.
        timestamp: UTC decision timestamp.
        record_hash: SHA-256 of all fields.
    """

    record_id: UUID
    context: OrderDecisionContext
    action_taken: str
    dossier: UncertaintyDossier
    timestamp: datetime
    record_hash: str = ""

    def __post_init__(self) -> None:
        if not self.action_taken:
            raise ValueError("action_taken must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.record_hash == "":
            object.__setattr__(self, "record_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "record_id": str(self.record_id),
                "context": self.context.to_hashable(),
                "action_taken": self.action_taken,
                "confidence_score": self.dossier.confidence_score,
                "timestamp": self.timestamp.isoformat(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# Item 3 — Schema-First Bus: contract validation of all event schemas
# ═══════════════════════════════════════════════════════════════════════════════
#
# Defines JSON schemas for all event types in the system and provides
# a validator that checks events against these schemas. The schema
# registry is the single source of truth for event contract validation.


class EventSchemaType(StrEnum):
    """All event types that flow through the event bus."""

    ORDER_CREATED = "order.created"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    ORDER_EXPIRED = "order.expired"
    RISK_ASSESSED = "risk.assessed"
    RISK_AUTHORIZED = "risk.authorized"
    RISK_DENIED = "risk.denied"
    RISK_RESERVED = "risk.reserved"
    RISK_CONSUMED = "risk.consumed"
    LEDGER_ENTRY_POSTED = "ledger.entry_posted"
    LEDGER_BALANCE_UPDATED = "ledger.balance_updated"
    FILL_RECORDED = "fill.recorded"


@dataclass(frozen=True)
class EventSchema:
    """A JSON schema for an event type.

    Attributes:
        schema_type: The event type this schema validates.
        version: Schema version (monotonically increasing).
        schema_json: The JSON schema dict.
    """

    schema_type: EventSchemaType
    version: int
    schema_json: dict[str, Any] = field(compare=False)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version must be >= 1.")


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating an event against a schema.

    Attributes:
        valid: True if the event is valid.
        schema_type: The schema type validated against.
        errors: List of validation errors (empty if valid).
    """

    valid: bool
    schema_type: EventSchemaType
    errors: list[str] = field(default_factory=list, compare=False)

    def __post_init__(self) -> None:
        if not self.errors and not self.valid:
            object.__setattr__(self, "errors", ["Unknown validation failure."])


# ── Schema definitions ──


def _order_schema(event_type: str) -> dict[str, Any]:
    """Build a JSON schema for an order event."""
    return {
        "type": "object",
        "required": ["tenant_id", "symbol", "side", "quantity"],
        "properties": {
            "tenant_id": {"type": "string", "minLength": 1},
            "symbol": {"type": "string", "minLength": 1},
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "quantity": {"type": "string", "minLength": 1},
            "fill_count": {"type": "integer", "minimum": 0},
            "execution_state": {"type": "string"},
            "event_type": {"type": "string", "const": event_type},
        },
        "additionalProperties": True,
    }


def _risk_schema(event_type: str) -> dict[str, Any]:
    """Build a JSON schema for a risk event."""
    return {
        "type": "object",
        "required": ["tenant_id", "authorized"],
        "properties": {
            "tenant_id": {"type": "string", "minLength": 1},
            "authorized": {"type": "boolean"},
            "reason": {"type": "string"},
            "symbol": {"type": "string"},
            "event_type": {"type": "string", "const": event_type},
        },
        "additionalProperties": True,
    }


def _ledger_schema(event_type: str) -> dict[str, Any]:
    """Build a JSON schema for a ledger event."""
    return {
        "type": "object",
        "required": ["tenant_id", "asset"],
        "properties": {
            "tenant_id": {"type": "string", "minLength": 1},
            "asset": {"type": "string", "minLength": 1},
            "amount": {"type": "string"},
            "entry_type": {"type": "string"},
            "event_type": {"type": "string", "const": event_type},
        },
        "additionalProperties": True,
    }


def _fill_schema() -> dict[str, Any]:
    """Build a JSON schema for a fill event."""
    return {
        "type": "object",
        "required": ["tenant_id", "symbol", "filled_quantity", "fill_price"],
        "properties": {
            "tenant_id": {"type": "string", "minLength": 1},
            "symbol": {"type": "string", "minLength": 1},
            "filled_quantity": {"type": "string", "minLength": 1},
            "fill_price": {"type": "string", "minLength": 1},
            "fee": {"type": "string"},
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "event_type": {"type": "string", "const": "fill.recorded"},
        },
        "additionalProperties": True,
    }


def build_all_event_schemas() -> dict[EventSchemaType, EventSchema]:
    """Build and return the JSON schemas for all event types.

    This is the single source of truth for event contract validation.
    Every event that flows through the Redis Streams event bus must
    conform to its registered schema.
    """
    schemas: dict[EventSchemaType, EventSchema] = {}
    for et in EventSchemaType:
        if et.value.startswith("order."):
            schemas[et] = EventSchema(
                schema_type=et,
                version=1,
                schema_json=_order_schema(et.value),
            )
        elif et.value.startswith("risk."):
            schemas[et] = EventSchema(
                schema_type=et,
                version=1,
                schema_json=_risk_schema(et.value),
            )
        elif et.value.startswith("ledger."):
            schemas[et] = EventSchema(
                schema_type=et,
                version=1,
                schema_json=_ledger_schema(et.value),
            )
        elif et.value == "fill.recorded":
            schemas[et] = EventSchema(
                schema_type=et,
                version=1,
                schema_json=_fill_schema(),
            )
    return schemas


def compute_context_hash(context: dict[str, Any]) -> str:
    """Compute a SHA-256 hash of a decision context for replay matching."""
    payload = json.dumps(context, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
