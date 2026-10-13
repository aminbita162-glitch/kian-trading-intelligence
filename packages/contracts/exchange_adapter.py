"""Exchange adapter protocol for production execution.

Per AD-005 (Multi-Provider Financial Connectivity): use approved provider
adapters for exchange connections. The execution engine must depend on a
protocol, not a concrete simulator — the simulator lives outside the
deployable image (E3 — Structure and Verification Separation).

Per Section 05.5: each approved adapter must define supported products and
operations; order submission and cancellation; order status and partial
fills; client order identifiers; rate limits; recovery and reconciliation
behavior. No exchange is automatically approved for live use.

Per AD-014: deterministic execution and reconciliation with idempotency,
partial-fill handling, and unknown-outcome reconciliation.
"""

from __future__ import annotations

from typing import Protocol

from contracts.enums import OrderState
from contracts.exchange import (
    ClientOrderId,
    ExchangeOrder,
    ExchangeSubmissionResult,
    OrderType,
)
from contracts.order import OrderIntent


class ExchangeAdapter(Protocol):
    """Protocol for exchange adapters used by the execution engine.

    The execution engine depends on this protocol, not a concrete class.
    The concrete ExchangeSimulator implementation lives in the simulation
    package (outside the deployable services/ tree).

    Per Section 05.5: approved adapter with supported operations, order
    submission/cancellation, status, partial fills, idempotency, rate
    limits, recovery and reconciliation.
    """

    @property
    def is_connected(self) -> bool: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def submit_order(
        self,
        intent: OrderIntent,
        *,
        order_type: OrderType = OrderType.MARKET,
        price: str | None = None,
        client_order_id: ClientOrderId | None = None,
    ) -> ExchangeSubmissionResult: ...

    def cancel_order(self, client_order_id: ClientOrderId) -> ExchangeOrder: ...

    def get_order(self, client_order_id: ClientOrderId) -> ExchangeOrder: ...

    def get_order_state(self, client_order_id: ClientOrderId) -> OrderState: ...

    def reconcile_order(self, client_order_id: ClientOrderId) -> ExchangeOrder: ...

    def get_all_orders(self, tenant_id: str | None = None) -> list[ExchangeOrder]: ...

    def reset(self) -> None: ...
