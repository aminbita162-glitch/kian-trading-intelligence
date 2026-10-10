"""Tests for the execution engine (Phase 04).

Per Section 05.1: mandatory execution pipeline.
Per AD-004: no exposure-increasing order may reach the exchange adapter
without valid risk authorization.
Per AD-014: deterministic execution, idempotency, partial-fill handling,
unknown-outcome reconciliation.
"""

import pytest

from contracts.enums import OrderState
from contracts.exchange import ClientOrderId, OrderType
from contracts.order import OrderIntent
from contracts.risk import AuthorizationStatus, RiskPolicy
from services.execution.engine import (
    ExecutionEngine,
    ExecutionError,
    RiskDeniedError,
)
from services.execution.exchange_simulator import ExchangeSimulator
from services.risk_kernel.kernel import RiskKernel


@pytest.fixture
def engine() -> ExecutionEngine:
    """Fresh execution engine with connected exchange and active policy."""
    kernel = RiskKernel()

    policy = RiskPolicy.create(
        tenant_id="tenant-1",
        max_concentration_pct="100.0",
        max_position_per_symbol=10000,
    ).activate()
    kernel.register_policy(policy)

    exchange = ExchangeSimulator()
    exchange.connect()

    return ExecutionEngine(risk_kernel=kernel, exchange=exchange)


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


class TestExecutionPipeline:
    def test_execute_market_order(self, engine: ExecutionEngine) -> None:
        intent = _make_intent()
        result = engine.execute_order(intent, current_price="50000.00")
        assert result.state is OrderState.FILLED
        assert len(result.fills) == 1

    def test_execute_limit_order(self, engine: ExecutionEngine) -> None:
        intent = _make_intent()
        result = engine.execute_order(
            intent,
            current_price="50000.00",
            order_type=OrderType.LIMIT,
            price="49000.00",
        )
        assert result.state is OrderState.FILLED
        assert result.fills[0].fill_price == "49000.00"

    def test_sell_order_executed(self, engine: ExecutionEngine) -> None:
        intent = _make_intent(side="sell")
        result = engine.execute_order(intent, current_price="50000.00")
        assert result.state is OrderState.FILLED
        assert result.fills[0].side == "sell"

    def test_risk_denied_blocks_execution(self) -> None:
        kernel = RiskKernel()

        policy = RiskPolicy.create(tenant_id="tenant-1", max_position_value="1000.00").activate()
        kernel.register_policy(policy)
        exchange = ExchangeSimulator()
        exchange.connect()
        eng = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        intent = _make_intent(quantity="1.0")  # 1 * 50000 = 50000 > 1000
        with pytest.raises(RiskDeniedError):
            eng.execute_order(intent, current_price="50000.00")

    def test_no_exchange_connection_raises(self) -> None:
        kernel = RiskKernel()

        policy = RiskPolicy.create(tenant_id="tenant-1").activate()
        kernel.register_policy(policy)
        exchange = ExchangeSimulator()
        # Not connected
        eng = ExecutionEngine(risk_kernel=kernel, exchange=exchange)
        intent = _make_intent()
        with pytest.raises(ExecutionError, match="not connected"):
            eng.execute_order(intent, current_price="50000.00")


class TestIdempotency:
    def test_same_client_id_returns_same_order(self, engine: ExecutionEngine) -> None:
        intent = _make_intent()
        cid = ClientOrderId("idempotency-exec-1")
        result1 = engine.execute_order(intent, current_price="50000.00", client_order_id=cid)
        intent2 = _make_intent()
        result2 = engine.execute_order(intent2, current_price="50000.00", client_order_id=cid)
        assert result1.exchange_order_id == result2.exchange_order_id

    def test_different_client_ids_different_orders(self, engine: ExecutionEngine) -> None:
        intent1 = _make_intent()
        result1 = engine.execute_order(
            intent1, current_price="50000.00", client_order_id=ClientOrderId("e1")
        )
        intent2 = _make_intent()
        result2 = engine.execute_order(
            intent2, current_price="50000.00", client_order_id=ClientOrderId("e2")
        )
        assert result1.exchange_order_id != result2.exchange_order_id


class TestPartialFillHandling:
    def test_partial_fill_in_pipeline(self) -> None:
        kernel = RiskKernel()

        policy = RiskPolicy.create(tenant_id="tenant-1", max_position_value="1000000.00").activate()
        kernel.register_policy(policy)
        exchange = ExchangeSimulator(partial_fill_probability=1.0)
        exchange.connect()
        eng = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        intent = _make_intent(quantity="2.0")
        result = eng.execute_order(intent, current_price="50000.00")
        assert result.state is OrderState.PARTIALLY_FILLED
        assert result.fills[0].is_partial


class TestUnknownOutcomeReconciliation:
    def test_unknown_outcome_in_pipeline(self) -> None:
        kernel = RiskKernel()

        policy = RiskPolicy.create(tenant_id="tenant-1", max_position_value="1000000.00").activate()
        kernel.register_policy(policy)
        exchange = ExchangeSimulator(unknown_outcome_probability=1.0)
        exchange.connect()
        eng = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        intent = _make_intent()
        result = eng.execute_order(intent, current_price="50000.00")
        assert result.state is OrderState.UNKNOWN_OUTCOME
        assert result.is_uncertain

    def test_reconcile_resolves_unknown(self) -> None:
        kernel = RiskKernel()

        policy = RiskPolicy.create(tenant_id="tenant-1", max_position_value="1000000.00").activate()
        kernel.register_policy(policy)
        exchange = ExchangeSimulator(unknown_outcome_probability=1.0)
        exchange.connect()
        eng = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        intent = _make_intent()
        cid = ClientOrderId("reconcile-test-1")
        result = eng.execute_order(intent, current_price="50000.00", client_order_id=cid)
        assert result.state is OrderState.UNKNOWN_OUTCOME

        # Reconcile
        order = eng.reconcile_order(cid)
        assert order.state is OrderState.FILLED

    def test_reconcile_limit_to_cancelled(self) -> None:
        kernel = RiskKernel()

        policy = RiskPolicy.create(tenant_id="tenant-1", max_position_value="1000000.00").activate()
        kernel.register_policy(policy)
        exchange = ExchangeSimulator(unknown_outcome_probability=1.0)
        exchange.connect()
        eng = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        intent = _make_intent()
        cid = ClientOrderId("reconcile-limit-1")
        eng.execute_order(
            intent,
            current_price="50000.00",
            order_type=OrderType.LIMIT,
            price="49000.00",
            client_order_id=cid,
        )
        order = eng.reconcile_order(cid)
        assert order.state is OrderState.CANCELLED


class TestAuthorizationConsumption:
    def test_filled_order_consumes_auth(self, engine: ExecutionEngine) -> None:
        intent = _make_intent()
        result = engine.execute_order(intent, current_price="50000.00")
        assert result.state is OrderState.FILLED

        auth = engine.risk_kernel.get_authorization_for_intent(str(intent.intent_id))
        assert auth.status is AuthorizationStatus.CONSUMED

    def test_denied_order_does_not_consume(self) -> None:
        kernel = RiskKernel()

        policy = RiskPolicy.create(
            tenant_id="tenant-1",
            max_position_value="100.00",
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        kernel.register_policy(policy)
        exchange = ExchangeSimulator()
        exchange.connect()
        eng = ExecutionEngine(risk_kernel=kernel, exchange=exchange)

        intent = _make_intent()
        with pytest.raises(RiskDeniedError):
            eng.execute_order(intent, current_price="50000.00")

        auth = eng.risk_kernel.get_authorization_for_intent(str(intent.intent_id))
        assert auth.status is AuthorizationStatus.DENIED


class TestEmergencyStopIntegration:
    def test_emergency_stop_blocks_execution(self, engine: ExecutionEngine) -> None:
        engine.risk_kernel.activate_emergency_stop("test emergency")
        intent = _make_intent()
        with pytest.raises(RiskDeniedError):
            engine.execute_order(intent, current_price="50000.00")

    def test_emergency_stop_allows_sells(self, engine: ExecutionEngine) -> None:
        engine.risk_kernel.activate_emergency_stop("test")
        intent = _make_intent(side="sell")
        result = engine.execute_order(intent, current_price="50000.00")
        assert result.state is OrderState.FILLED

    def test_deactivate_then_execute(self, engine: ExecutionEngine) -> None:
        engine.risk_kernel.activate_emergency_stop("test")
        intent = _make_intent()
        with pytest.raises(RiskDeniedError):
            engine.execute_order(intent, current_price="50000.00")
        engine.risk_kernel.deactivate_emergency_stop()
        intent2 = _make_intent()
        result = engine.execute_order(intent2, current_price="50000.00")
        assert result.state is OrderState.FILLED
