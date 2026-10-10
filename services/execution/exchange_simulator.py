"""Exchange simulator for Kian Trading Intelligence.

Per AD-023 (Digital Twin): deterministic simulation, exchange emulation, replay,
fault injection, and repeatable verification before live operations.

Per Section 05.5: each approved adapter must define supported products and
operations; order submission and cancellation; order status and partial
fills; client order identifiers; rate limits; recovery and reconciliation
behavior.

Per AD-014: deterministic execution and reconciliation with idempotency,
partial-fill handling, and unknown-outcome reconciliation.

Per Section 05.3: timeouts must not trigger blind order resubmission. Unknown
outcomes require exchange reconciliation. If safe reconciliation is impossible,
new exposure-increasing operations must stop.

No exchange is automatically approved for live use (Section 05.5).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from threading import Lock

from contracts.enums import OrderState
from contracts.exchange import (
    ClientOrderId,
    ExchangeOrder,
    ExchangeOrderId,
    ExchangeSubmissionResult,
    FillResult,
    OrderType,
)
from contracts.order import OrderIntent


class ExchangeAdapterError(Exception):
    """Base exception for exchange adapter errors."""


class OrderNotFoundError(ExchangeAdapterError):
    """Raised when an order is not found."""


class DuplicateOrderError(ExchangeAdapterError):
    """Raised when a duplicate client order ID is submitted.

    Per Section 05.3: idempotency — same client order ID returns the
    existing order, not a new one.
    """


class ExchangeNotConnectedError(ExchangeAdapterError):
    """Raised when the exchange adapter is not connected."""


class ReconciliationRequired(ExchangeAdapterError):
    """Raised when an order has an unknown outcome requiring reconciliation."""


class ExchangeSimulator:
    """Deterministic exchange simulator for testing and simulation mode.

    Per AD-023: deterministic simulation and exchange emulation.
    Per Section 01.3: SIMULATION mode uses synthetic data without real
    financial orders.

    Features:
    - Deterministic fill prices from SHA-256 hashing.
    - Idempotent order submission via client order IDs.
    - Configurable partial-fill behavior.
    - Unknown-outcome simulation for reconciliation testing.
    - Order cancellation.
    - Order status queries.
    - Reconciliation for uncertain outcomes.
    """

    def __init__(
        self,
        *,
        fill_latency_ms: int = 0,
        partial_fill_probability: float = 0.0,
        unknown_outcome_probability: float = 0.0,
    ) -> None:
        self._connected: bool = False
        self._fill_latency_ms: int = fill_latency_ms
        self._partial_fill_probability: float = partial_fill_probability
        self._unknown_outcome_probability: float = unknown_outcome_probability
        self._orders: dict[str, ExchangeOrder] = {}  # client_order_id -> order
        self._client_id_to_exchange: dict[str, ExchangeOrderId] = {}
        self._lock: Lock = Lock()

    @property
    def is_connected(self) -> bool:
        """True if the simulator is connected."""
        return self._connected

    def connect(self) -> None:
        """Connect to the simulated exchange."""
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect from the simulated exchange."""
        self._connected = False

    def _check_connection(self) -> None:
        """Raise if not connected."""
        if not self._connected:
            raise ExchangeNotConnectedError("Exchange simulator is not connected.")

    def _deterministic_price(self, seed: str) -> str:
        """Generate a deterministic fill price from a seed."""
        h = hashlib.sha256(seed.encode()).hexdigest()
        raw = int(h[:8], 16)
        price = 50000.0 * (0.9 + (raw / 0xFFFFFFFF) * 0.2)
        return str(price)

    def _should_partial_fill(self, client_order_id: str) -> bool:
        """Deterministically decide if an order should partially fill."""
        if self._partial_fill_probability <= 0:
            return False
        h = hashlib.sha256(f"partial:{client_order_id}".encode()).hexdigest()
        val = int(h[:8], 16) / 0xFFFFFFFF
        return val < self._partial_fill_probability

    def _should_unknown_outcome(self, client_order_id: str) -> bool:
        """Deterministically decide if an order should have an unknown outcome."""
        if self._unknown_outcome_probability <= 0:
            return False
        h = hashlib.sha256(f"unknown:{client_order_id}".encode()).hexdigest()
        val = int(h[:8], 16) / 0xFFFFFFFF
        return val < self._unknown_outcome_probability

    def submit_order(
        self,
        intent: OrderIntent,
        *,
        order_type: OrderType = OrderType.MARKET,
        price: str | None = None,
        client_order_id: ClientOrderId | None = None,
    ) -> ExchangeSubmissionResult:
        """Submit an order to the exchange simulator.

        Per Section 05.3: idempotency — if the same client_order_id is
        submitted again, return the existing order without creating a
        duplicate. Timeouts must not trigger blind resubmission.

        Per AD-014: deterministic execution with idempotency and
        partial-fill handling.
        """
        self._check_connection()

        cid = client_order_id or ClientOrderId(str(intent.intent_id))
        cid_str = str(cid)

        with self._lock:
            # Idempotency check: return existing order if already submitted
            existing = self._orders.get(cid_str)
            if existing is not None:
                return ExchangeSubmissionResult(
                    client_order_id=cid,
                    exchange_order_id=existing.exchange_order_id,
                    state=existing.state,
                    fills=list(existing.fills),
                    timestamp=datetime.now(UTC),
                )

            # Create exchange order
            exchange_order = ExchangeOrder(
                client_order_id=cid,
                exchange_order_id=ExchangeOrderId.generate(),
                tenant_id=intent.tenant_id,
                intent_id=str(intent.intent_id),
                symbol=intent.symbol,
                side=intent.side,
                order_type=order_type,
                quantity=intent.quantity,
                price=price,
                state=OrderState.SUBMITTED,
            )
            self._orders[cid_str] = exchange_order
            assert exchange_order.exchange_order_id is not None
            self._client_id_to_exchange[cid_str] = exchange_order.exchange_order_id

            # Simulate unknown outcome
            if self._should_unknown_outcome(cid_str):
                exchange_order.transition_to(OrderState.UNKNOWN_OUTCOME)
                return ExchangeSubmissionResult(
                    client_order_id=cid,
                    exchange_order_id=exchange_order.exchange_order_id,
                    state=OrderState.UNKNOWN_OUTCOME,
                    fills=[],
                    error="Exchange returned unknown outcome — reconciliation required.",
                    timestamp=datetime.now(UTC),
                )

            # Simulate fill(s)
            fill_price = price or self._deterministic_price(cid_str)
            fills: list[FillResult] = []

            if self._should_partial_fill(cid_str):
                # Partial fill: fill half the quantity
                total_qty = Decimal(intent.quantity)
                partial_qty = total_qty / Decimal(2)
                fill = FillResult(
                    fill_id=f"fill-{cid_str}-partial",
                    client_order_id=cid,
                    symbol=intent.symbol,
                    side=intent.side,
                    filled_quantity=str(partial_qty),
                    fill_price=fill_price,
                    timestamp=datetime.now(UTC),
                    is_partial=True,
                )
                fills.append(fill)
                exchange_order.add_fill(fill)
                exchange_order.transition_to(OrderState.PARTIALLY_FILLED)
            else:
                # Full fill
                fill = FillResult(
                    fill_id=f"fill-{cid_str}",
                    client_order_id=cid,
                    symbol=intent.symbol,
                    side=intent.side,
                    filled_quantity=intent.quantity,
                    fill_price=fill_price,
                    timestamp=datetime.now(UTC),
                    is_partial=False,
                )
                fills.append(fill)
                exchange_order.add_fill(fill)
                exchange_order.transition_to(OrderState.FILLED)

            return ExchangeSubmissionResult(
                client_order_id=cid,
                exchange_order_id=exchange_order.exchange_order_id,
                state=exchange_order.state,
                fills=fills,
                timestamp=datetime.now(UTC),
            )

    def cancel_order(self, client_order_id: ClientOrderId) -> ExchangeOrder:
        """Cancel an order on the exchange.

        Per AD-014: cancellation must be idempotent and must not create
        duplicate financial effects.
        """
        self._check_connection()
        cid_str = str(client_order_id)

        with self._lock:
            order = self._orders.get(cid_str)
            if order is None:
                raise OrderNotFoundError(f"Order {cid_str} not found.")

            # Terminal states cannot be cancelled
            if order.state in (
                OrderState.FILLED,
                OrderState.CANCELLED,
                OrderState.REJECTED,
                OrderState.EXPIRED,
            ):
                return order

            order.transition_to(OrderState.CANCELLED)
            return order

    def get_order(self, client_order_id: ClientOrderId) -> ExchangeOrder:
        """Get the current state of an order."""
        self._check_connection()
        cid_str = str(client_order_id)
        with self._lock:
            order = self._orders.get(cid_str)
            if order is None:
                raise OrderNotFoundError(f"Order {cid_str} not found.")
            return order

    def get_order_state(self, client_order_id: ClientOrderId) -> OrderState:
        """Get the current state of an order."""
        return self.get_order(client_order_id).state

    def reconcile_order(self, client_order_id: ClientOrderId) -> ExchangeOrder:
        """Reconcile an order with an unknown outcome.

        Per Section 05.3: unknown outcomes require exchange reconciliation.
        If safe reconciliation is impossible, new exposure-increasing
        operations must stop.

        Per Section 05.6: emergency stop preserves order and financial
        evidence and initiates reconciliation.
        """
        self._check_connection()
        cid_str = str(client_order_id)

        with self._lock:
            order = self._orders.get(cid_str)
            if order is None:
                raise OrderNotFoundError(f"Order {cid_str} not found.")

            if order.state is not OrderState.UNKNOWN_OUTCOME:
                return order

            # Reconciliation: determine the actual outcome deterministically
            # For the simulator, we deterministically resolve to FILLED
            # if the order was a market order, or CANCELLED if it was a limit.
            if order.order_type is OrderType.MARKET:
                fill_price = self._deterministic_price(cid_str)
                fill = FillResult(
                    fill_id=f"fill-{cid_str}-reconciled",
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    side=order.side,
                    filled_quantity=order.quantity,
                    fill_price=fill_price,
                    timestamp=datetime.now(UTC),
                    is_partial=False,
                )
                order.add_fill(fill)
                order.transition_to(OrderState.FILLED)
            else:
                order.transition_to(OrderState.CANCELLED)

            return order

    def get_all_orders(self, tenant_id: str | None = None) -> list[ExchangeOrder]:
        """Get all orders, optionally filtered by tenant."""
        with self._lock:
            orders = list(self._orders.values())
            if tenant_id is not None:
                orders = [o for o in orders if o.tenant_id == tenant_id]
            return orders

    def reset(self) -> None:
        """Reset the simulator state (for testing)."""
        with self._lock:
            self._orders.clear()
            self._client_id_to_exchange.clear()
            self._connected = False
