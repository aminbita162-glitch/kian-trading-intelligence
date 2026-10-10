"""Tests for the exchange simulator (Phase 04).

Per AD-023: deterministic simulation and exchange emulation.
Per Section 05.3: idempotency, partial-fill handling, unknown-outcome
reconciliation.
Per AD-014: deterministic execution and reconciliation.
"""

import pytest

from contracts.enums import OrderState
from contracts.exchange import (
    ClientOrderId,
    FillResult,
    OrderType,
)
from contracts.order import OrderIntent
from services.execution.exchange_simulator import (
    ExchangeNotConnectedError,
    ExchangeSimulator,
    OrderNotFoundError,
)


@pytest.fixture
def exchange() -> ExchangeSimulator:
    """Connected exchange simulator."""
    sim = ExchangeSimulator()
    sim.connect()
    return sim


@pytest.fixture
def exchange_partial() -> ExchangeSimulator:
    """Connected exchange with partial fill enabled."""
    sim = ExchangeSimulator(partial_fill_probability=1.0)
    sim.connect()
    return sim


@pytest.fixture
def exchange_unknown() -> ExchangeSimulator:
    """Connected exchange with unknown outcome enabled."""
    sim = ExchangeSimulator(unknown_outcome_probability=1.0)
    sim.connect()
    return sim


def _make_intent(**overrides: object) -> OrderIntent:
    defaults: dict[str, object] = {
        "tenant_id": "tenant-1",
        "profile_id": "p1",
        "symbol": "BTC/USDT",
        "side": "buy",
        "quantity": "1.0",
    }
    defaults.update(overrides)
    return OrderIntent.create(**defaults)  # type: ignore[arg-type]


class TestExchangeConnection:
    def test_connect(self) -> None:
        sim = ExchangeSimulator()
        assert not sim.is_connected
        sim.connect()
        assert sim.is_connected

    def test_disconnect(self) -> None:
        sim = ExchangeSimulator()
        sim.connect()
        assert sim.is_connected
        sim.disconnect()
        assert not sim.is_connected

    def test_submit_when_disconnected_raises(self) -> None:
        sim = ExchangeSimulator()
        intent = _make_intent()
        with pytest.raises(ExchangeNotConnectedError):
            sim.submit_order(intent)


class TestOrderSubmission:
    def test_submit_market_order_filled(self, exchange: ExchangeSimulator) -> None:
        intent = _make_intent()
        result = exchange.submit_order(intent)
        assert result.state is OrderState.FILLED
        assert len(result.fills) == 1
        assert result.exchange_order_id is not None

    def test_submit_limit_order(self, exchange: ExchangeSimulator) -> None:
        intent = _make_intent()
        result = exchange.submit_order(
            intent,
            order_type=OrderType.LIMIT,
            price="49000.00",
        )
        assert result.state is OrderState.FILLED
        assert result.fills[0].fill_price == "49000.00"

    def test_deterministic_fill_price(self, exchange: ExchangeSimulator) -> None:
        """Same client order ID produces the same fill price."""
        intent1 = _make_intent()
        cid = ClientOrderId("deterministic-test-1")
        result1 = exchange.submit_order(intent1, client_order_id=cid)
        # Reset and resubmit with the same CID
        exchange.reset()
        exchange.connect()
        intent2 = _make_intent()
        result2 = exchange.submit_order(intent2, client_order_id=cid)
        assert result1.fills[0].fill_price == result2.fills[0].fill_price

    def test_sell_order_filled(self, exchange: ExchangeSimulator) -> None:
        intent = _make_intent(side="sell")
        result = exchange.submit_order(intent)
        assert result.state is OrderState.FILLED
        assert result.fills[0].side == "sell"


class TestIdempotency:
    def test_duplicate_client_order_id_returns_existing(self, exchange: ExchangeSimulator) -> None:
        intent = _make_intent()
        cid = ClientOrderId("idempotency-test-1")
        result1 = exchange.submit_order(intent, client_order_id=cid)
        # Submit again with the same CID
        intent2 = _make_intent()
        result2 = exchange.submit_order(intent2, client_order_id=cid)
        # Should return the same order, not a new one
        assert result1.exchange_order_id == result2.exchange_order_id
        assert result1.state == result2.state

    def test_different_client_ids_create_different_orders(
        self, exchange: ExchangeSimulator
    ) -> None:
        intent1 = _make_intent()
        result1 = exchange.submit_order(intent1, client_order_id=ClientOrderId("cid-1"))
        intent2 = _make_intent()
        result2 = exchange.submit_order(intent2, client_order_id=ClientOrderId("cid-2"))
        assert result1.exchange_order_id != result2.exchange_order_id


class TestPartialFills:
    def test_partial_fill_state(self, exchange_partial: ExchangeSimulator) -> None:
        intent = _make_intent(quantity="2.0")
        result = exchange_partial.submit_order(intent)
        assert result.state is OrderState.PARTIALLY_FILLED
        assert len(result.fills) == 1
        assert result.fills[0].is_partial

    def test_partial_fill_half_quantity(self, exchange_partial: ExchangeSimulator) -> None:
        intent = _make_intent(quantity="2.0")
        result = exchange_partial.submit_order(intent)
        # Should fill half = 1.0
        assert float(result.fills[0].filled_quantity) == 1.0

    def test_partial_fill_remaining(self, exchange_partial: ExchangeSimulator) -> None:
        intent = _make_intent(quantity="2.0")
        cid = ClientOrderId("partial-test-1")
        exchange_partial.submit_order(intent, client_order_id=cid)
        order = exchange_partial.get_order(cid)
        assert order.is_partially_filled
        assert float(order.remaining_quantity) == 1.0


class TestUnknownOutcome:
    def test_unknown_outcome_state(self, exchange_unknown: ExchangeSimulator) -> None:
        intent = _make_intent()
        result = exchange_unknown.submit_order(intent)
        assert result.state is OrderState.UNKNOWN_OUTCOME
        assert result.is_uncertain
        assert len(result.fills) == 0

    def test_reconcile_market_order_to_filled(self, exchange_unknown: ExchangeSimulator) -> None:
        intent = _make_intent()
        cid = ClientOrderId("unknown-test-1")
        result = exchange_unknown.submit_order(intent, client_order_id=cid)
        assert result.state is OrderState.UNKNOWN_OUTCOME
        # Reconcile
        order = exchange_unknown.reconcile_order(cid)
        assert order.state is OrderState.FILLED
        assert len(order.fills) > 0

    def test_reconcile_limit_order_to_cancelled(self) -> None:
        sim = ExchangeSimulator(unknown_outcome_probability=1.0)
        sim.connect()
        intent = _make_intent()
        cid = ClientOrderId("unknown-limit-1")
        sim.submit_order(
            intent,
            order_type=OrderType.LIMIT,
            price="49000.00",
            client_order_id=cid,
        )
        order = sim.reconcile_order(cid)
        assert order.state is OrderState.CANCELLED


class TestOrderCancellation:
    def test_cancel_order(self, exchange: ExchangeSimulator) -> None:
        # Use an unknown outcome exchange to get a non-terminal order
        sim = ExchangeSimulator(unknown_outcome_probability=1.0)
        sim.connect()
        intent = _make_intent()
        cid = ClientOrderId("cancel-test-1")
        sim.submit_order(intent, client_order_id=cid)
        order = sim.cancel_order(cid)
        assert order.state is OrderState.CANCELLED

    def test_cancel_filled_order_idempotent(self, exchange: ExchangeSimulator) -> None:
        intent = _make_intent()
        cid = ClientOrderId("cancel-filled-1")
        exchange.submit_order(intent, client_order_id=cid)
        # Order is FILLED — cancelling should be idempotent (no error, state unchanged)
        order = exchange.cancel_order(cid)
        assert order.state is OrderState.FILLED

    def test_cancel_nonexistent_order_raises(self, exchange: ExchangeSimulator) -> None:
        with pytest.raises(OrderNotFoundError):
            exchange.cancel_order(ClientOrderId("nonexistent"))


class TestOrderQueries:
    def test_get_order(self, exchange: ExchangeSimulator) -> None:
        intent = _make_intent()
        cid = ClientOrderId("get-test-1")
        exchange.submit_order(intent, client_order_id=cid)
        order = exchange.get_order(cid)
        assert order.client_order_id == cid

    def test_get_order_state(self, exchange: ExchangeSimulator) -> None:
        intent = _make_intent()
        cid = ClientOrderId("state-test-1")
        exchange.submit_order(intent, client_order_id=cid)
        state = exchange.get_order_state(cid)
        assert state is OrderState.FILLED

    def test_get_all_orders_by_tenant(self, exchange: ExchangeSimulator) -> None:
        intent1 = _make_intent(tenant_id="tenant-1")
        intent2 = _make_intent(tenant_id="tenant-2")
        exchange.submit_order(intent1, client_order_id=ClientOrderId("t1-1"))
        exchange.submit_order(intent2, client_order_id=ClientOrderId("t2-1"))
        t1_orders = exchange.get_all_orders(tenant_id="tenant-1")
        assert len(t1_orders) == 1
        assert t1_orders[0].tenant_id == "tenant-1"

    def test_get_nonexistent_order_raises(self, exchange: ExchangeSimulator) -> None:
        with pytest.raises(OrderNotFoundError):
            exchange.get_order(ClientOrderId("nonexistent"))


class TestFillResult:
    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid side"):
            FillResult(
                fill_id="f1",
                client_order_id=ClientOrderId("c1"),
                symbol="BTC/USDT",
                side="invalid",
                filled_quantity="1.0",
                fill_price="50000.00",
            )

    def test_invalid_quantity_rejected(self) -> None:
        with pytest.raises(ValueError, match="filled_quantity must be positive"):
            FillResult(
                fill_id="f1",
                client_order_id=ClientOrderId("c1"),
                symbol="BTC/USDT",
                side="buy",
                filled_quantity="0",
                fill_price="50000.00",
            )

    def test_negative_fee_rejected(self) -> None:
        with pytest.raises(ValueError, match="fee must be non-negative"):
            FillResult(
                fill_id="f1",
                client_order_id=ClientOrderId("c1"),
                symbol="BTC/USDT",
                side="buy",
                filled_quantity="1.0",
                fill_price="50000.00",
                fee="-1.00",
            )
