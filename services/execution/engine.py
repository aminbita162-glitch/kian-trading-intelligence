"""Execution engine for Kian Trading Intelligence.

Per Section 05.1: the mandatory execution pipeline coordinates the Risk
Kernel, exchange adapter, and session state machine.

Per AD-004: the Execution & Supervisor Agent coordinates authorized order
lifecycle, exchange adapter orchestration, and reconciliation. It is
prohibited from bypassing risk authorization.

Per AD-014: deterministic execution and reconciliation with idempotency,
partial-fill handling, and unknown-outcome reconciliation.

Per Section 05.6: emergency stop blocks new exposure-increasing orders,
prevents automatic trading restart, preserves order and financial evidence,
initiates reconciliation, and applies only preauthorized protective actions.
"""

from __future__ import annotations

from contracts.enums import OrderState
from contracts.exchange import (
    ClientOrderId,
    ExchangeOrder,
    ExchangeSubmissionResult,
    OrderType,
)
from contracts.order import OrderIntent
from contracts.risk import (
    AuthorizationStatus,
)
from contracts.trading import TradingSession
from services.execution.exchange_simulator import (
    ExchangeSimulator,
)
from services.risk_kernel.kernel import (
    RiskKernel,
)


class ExecutionError(Exception):
    """Base exception for execution engine errors."""


class RiskDeniedError(ExecutionError):
    """Raised when the risk kernel denies an order."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Risk authorization denied: {reason}")
        self.reason = reason


class OrderNotInValidStateException(ExecutionError):
    """Raised when an order is not in a valid state for the requested operation."""


class UnknownOutcomeUnresolvedError(ExecutionError):
    """Raised when an unknown outcome cannot be safely resolved."""


class ExecutionEngine:
    """Coordinates the mandatory execution pipeline (Section 05.1).

    The execution engine enforces the invariant: no exposure-increasing
    order may reach the exchange adapter without valid risk authorization.

    Per AD-014: deterministic execution with idempotency, partial-fill
    handling, and unknown-outcome reconciliation.
    """

    def __init__(
        self,
        *,
        risk_kernel: RiskKernel,
        exchange: ExchangeSimulator,
    ) -> None:
        self._kernel: RiskKernel = risk_kernel
        self._exchange: ExchangeSimulator = exchange
        self._intent_to_client: dict[str, ClientOrderId] = {}
        self._client_to_intent: dict[str, str] = {}

    def execute_order(  # noqa: PLR0913
        self,
        intent: OrderIntent,
        *,
        current_price: str,
        session: TradingSession | None = None,
        order_type: OrderType = OrderType.MARKET,
        price: str | None = None,
        client_order_id: ClientOrderId | None = None,
    ) -> ExchangeSubmissionResult:
        """Execute an order through the full mandatory pipeline.

        Per Section 05.1:
        1. Generate trade intent (caller provides).
        2. Verify session authorization.
        3. Reserve risk capacity.
        4. Issue bounded risk authorization.
        5. Submit through exchange adapter.
        6. Record acknowledgement or uncertain outcome.

        Per AD-004: no exposure-increasing order may reach the exchange
        adapter without valid risk authorization.
        """
        # Step 1: Verify exchange is connected
        if not self._exchange.is_connected:
            raise ExecutionError("Exchange adapter is not connected.")

        # Step 2: Risk authorization
        auth = self._kernel.authorize(
            intent,
            current_price=current_price,
            session=session,
        )

        if auth.status is AuthorizationStatus.DENIED:
            raise RiskDeniedError(auth.reason)

        # Step 3: Reserve risk capacity
        reservation = self._kernel.reserve_capacity(auth)

        # Step 4: Submit to exchange
        cid = client_order_id or ClientOrderId(str(intent.intent_id))
        result = self._exchange.submit_order(
            intent,
            order_type=order_type,
            price=price,
            client_order_id=cid,
        )

        # Track the mapping
        self._intent_to_client[str(intent.intent_id)] = cid
        self._client_to_intent[str(cid)] = str(intent.intent_id)

        # Step 5: Handle result
        if result.state is OrderState.UNKNOWN_OUTCOME:
            # Per Section 05.3: unknown outcomes require reconciliation.
            # Do NOT blind-retry. Consume the reservation so capacity is held.
            self._kernel.consume_reservation(str(reservation.reservation_id))
            return result

        if result.state in (OrderState.FILLED, OrderState.PARTIALLY_FILLED):
            # Consume the authorization and reservation
            self._kernel.consume_authorization(str(auth.authorization_id))
            self._kernel.consume_reservation(str(reservation.reservation_id))

            # Record fills for exposure tracking
            for fill in result.fills:
                self._kernel.record_fill(intent.tenant_id, fill)

        elif result.state in (OrderState.REJECTED, OrderState.EXPIRED, OrderState.CANCELLED):
            # Release the reservation — order did not execute
            self._kernel.release_reservation(str(reservation.reservation_id))
            self._kernel.cancel_authorization(str(auth.authorization_id))

        return result

    def cancel_order(self, client_order_id: ClientOrderId) -> ExchangeOrder:
        """Cancel an order on the exchange.

        Per AD-014: cancellation is idempotent.
        """
        return self._exchange.cancel_order(client_order_id)

    def reconcile_order(self, client_order_id: ClientOrderId) -> ExchangeOrder:
        """Reconcile an order with an unknown outcome.

        Per Section 05.3: unknown outcomes require exchange reconciliation.
        If safe reconciliation is impossible, new exposure-increasing
        operations must stop.

        Per Section 05.6: emergency stop preserves order and financial
        evidence and initiates reconciliation.
        """
        order = self._exchange.reconcile_order(client_order_id)

        # If reconciliation resolves to FILLED, record the fills
        if order.state is OrderState.FILLED:
            for fill in order.fills:
                self._kernel.record_fill(order.tenant_id, fill)

        return order

    def get_order(self, client_order_id: ClientOrderId) -> ExchangeOrder:
        """Get the current state of an order."""
        return self._exchange.get_order(client_order_id)

    @property
    def risk_kernel(self) -> RiskKernel:
        """Access the risk kernel."""
        return self._kernel

    @property
    def exchange(self) -> ExchangeSimulator:
        """Access the exchange simulator."""
        return self._exchange
