"""Exchange adapter contracts for Kian Trading Intelligence.

Per Section 05.5: each approved adapter must define supported products and
operations; authentication scopes; order submission and cancellation; order
status and partial fills; client order identifiers; rate limits; protective
order capabilities; recovery and reconciliation behavior; provider
restrictions. No exchange is automatically approved for live use.

Per AD-014: deterministic execution and reconciliation with idempotency,
partial-fill handling, and unknown-outcome reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from contracts.enums import OrderState


class OrderSide(StrEnum):
    """Order side for exchange submission."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Order type for exchange submission."""

    MARKET = "market"
    LIMIT = "limit"


class FillStatus(StrEnum):
    """Status of a fill after exchange execution."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


@dataclass(frozen=True)
class ExchangeOrderId:
    """Stable identity for an exchange order."""

    value: UUID

    @classmethod
    def generate(cls) -> ExchangeOrderId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ClientOrderId:
    """Client-side order identifier for idempotency.

    Per Section 05.3: every trade intent and order submission must have a
    stable identity. The client order ID is the idempotency key for the
    exchange adapter.
    """

    value: str

    def __str__(self) -> str:
        return self.value


@dataclass
class FillResult:
    """Result of a fill or partial fill from the exchange.

    Per AD-014 (Deterministic Execution): explicit partial-fill handling.
    Per AD-018: exact decimal arithmetic.

    Attributes:
        fill_id: Stable fill identifier.
        client_order_id: Client order this fill belongs to.
        symbol: Trading symbol.
        side: Order side.
        filled_quantity: Quantity filled.
        fill_price: Execution price.
        fee: Exchange fee charged.
        timestamp: UTC fill timestamp.
        is_partial: True if this is a partial fill.
    """

    fill_id: str
    client_order_id: ClientOrderId
    symbol: str
    side: str
    filled_quantity: str
    fill_price: str
    fee: str = "0.00"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_partial: bool = False

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side!r}.")
        if float(self.filled_quantity) <= 0:
            raise ValueError("filled_quantity must be positive.")
        if float(self.fill_price) <= 0:
            raise ValueError("fill_price must be positive.")
        if float(self.fee) < 0:
            raise ValueError("fee must be non-negative.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class ExchangeSubmissionResult:
    """Result of submitting an order to the exchange.

    Per Section 05.3: record acknowledgement or uncertain outcome.

    Attributes:
        client_order_id: Client order identifier for idempotency.
        exchange_order_id: Exchange-assigned order ID (None if unknown).
        state: Order state after submission.
        fills: List of fills (may be empty).
        error: Error message if submission failed.
        timestamp: UTC result timestamp.
    """

    client_order_id: ClientOrderId
    exchange_order_id: ExchangeOrderId | None
    state: OrderState
    fills: list[FillResult] = field(default_factory=list)
    error: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")

    @property
    def total_filled(self) -> str:
        """Total quantity filled across all fills."""
        return str(sum(float(f.filled_quantity) for f in self.fills))

    @property
    def is_uncertain(self) -> bool:
        """True if the submission resulted in an unknown outcome."""
        return self.state is OrderState.UNKNOWN_OUTCOME


@dataclass
class ExchangeOrder:
    """An order tracked by the exchange adapter.

    Per AD-014: durable order state with unique identifiers.

    Attributes:
        client_order_id: Client-side idempotency key.
        exchange_order_id: Exchange-assigned order ID.
        tenant_id: Tenant scope.
        intent_id: Original order intent ID.
        symbol: Trading symbol.
        side: Order side.
        order_type: Order type (market/limit).
        quantity: Original order quantity.
        price: Limit price (None for market orders).
        state: Current order state.
        fills: List of fills received.
        created_at: UTC creation timestamp.
        updated_at: UTC last update timestamp.
    """

    client_order_id: ClientOrderId
    exchange_order_id: ExchangeOrderId | None
    tenant_id: str
    intent_id: str
    symbol: str
    side: str
    order_type: OrderType
    quantity: str
    price: str | None = None
    state: OrderState = OrderState.CREATED
    fills: list[FillResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side!r}.")
        if float(self.quantity) <= 0:
            raise ValueError("Quantity must be positive.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware (UTC).")

    @property
    def filled_quantity(self) -> str:
        """Total quantity filled so far."""
        return str(sum(float(f.filled_quantity) for f in self.fills))

    @property
    def remaining_quantity(self) -> str:
        """Remaining quantity to be filled."""
        return str(float(self.quantity) - float(self.filled_quantity))

    @property
    def is_fully_filled(self) -> bool:
        """True if the order is fully filled."""
        return float(self.filled_quantity) >= float(self.quantity)

    @property
    def is_partially_filled(self) -> bool:
        """True if the order is partially filled."""
        filled = float(self.filled_quantity)
        return 0 < filled < float(self.quantity)

    def transition_to(self, new_state: OrderState) -> None:
        """Update the order state and timestamp.

        The caller is responsible for verifying that the transition is legal
        per LEGAL_ORDER_TRANSITIONS.
        """
        self.state = new_state
        self.updated_at = datetime.now(UTC)

    def add_fill(self, fill: FillResult) -> None:
        """Add a fill to this order."""
        self.fills.append(fill)
        self.updated_at = datetime.now(UTC)
