"""Order intent contracts for Kian Trading Intelligence.

Per AD-014: deterministic execution, idempotency, and stable identity.
Per Section 05.3: every trade intent must have a stable identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from contracts.enums import OrderState


@dataclass(frozen=True)
class OrderIntentId:
    """Stable identity for a trade intent.

    Per Section 05.3: every trade intent must have a stable identity.
    This is a value object — two OrderIntentId values are equal iff
    their UUID values match.
    """

    value: UUID

    @classmethod
    def generate(cls) -> OrderIntentId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class OrderIntent:
    """A trade intent before risk authorization.

    Per AD-003: LLM output must not directly authorize or execute orders.
    Per AD-020: agent contracts require typed permissions and deterministic
    cross-verification.

    Attributes:
        intent_id: Stable unique identifier for the intent.
        tenant_id: Tenant scope identifier.
        profile_id: Trading profile identifier.
        symbol: Trading symbol (e.g., "BTC/USDT").
        side: Order side — "buy" or "sell".
        quantity: Order quantity in base currency.
        created_at: UTC timestamp of creation.
        state: Current order state (default CREATED).
        idempotency_key: Optional key for idempotent submission.
    """

    intent_id: OrderIntentId
    tenant_id: str
    profile_id: str
    symbol: str
    side: str
    quantity: str  # Use string for exact decimal representation
    created_at: datetime
    state: OrderState = OrderState.CREATED
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side!r}. Must be 'buy' or 'sell'.")
        if float(self.quantity) <= 0:
            raise ValueError("Quantity must be positive.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        profile_id: str,
        symbol: str,
        side: str,
        quantity: str,
        idempotency_key: str | None = None,
    ) -> OrderIntent:
        """Create a new order intent in the CREATED state."""
        return cls(
            intent_id=OrderIntentId.generate(),
            tenant_id=tenant_id,
            profile_id=profile_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            created_at=datetime.now(UTC),
            state=OrderState.CREATED,
            idempotency_key=idempotency_key,
        )
