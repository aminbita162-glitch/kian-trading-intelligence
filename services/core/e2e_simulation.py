"""End-to-end simulation scenario — Phase A: Real Infrastructure.

Per DIRECTIV.txt V1.4 Phase A: "Implement and verify one end-to-end
simulation scenario: a single tenant submits an order that flows from
agent through Risk Kernel to ledger with real persistence."

This module orchestrates the full simulation pipeline:

  1. A tenant submits an order intent (agent layer).
  2. The Risk Kernel assesses and authorizes the order.
  3. The Execution Engine submits to the simulated exchange.
  4. The fill is recorded in the persistent ledger (PostgreSQL).
  5. An event is emitted to the DB transactional outbox.
  6. The Redis Stream bus relays the outbox event to Redis Streams.
  7. The event is consumed from Redis and delivered to the inbox.

All data is synthetic. No real money, no real exchange keys (Section 00.3).
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from contracts.enums import OrderState
from contracts.order import OrderIntent
from contracts.risk import AuthorizationStatus, RiskPolicy
from services.core.redis_bus import (
    STREAM_ORDER_EVENTS,
    StreamEvent,
)
from services.execution.engine import ExecutionEngine
from services.ledger.persistent_ledger import PersistentLedger
from services.risk_kernel.persistent_kernel import PersistentRiskKernel

if TYPE_CHECKING:
    from services.core.redis_bus import RedisStreamBus

logger = logging.getLogger(__name__)


@dataclass
class SimulationScenarioResult:
    """Result of the end-to-end simulation scenario."""

    tenant_id: str
    order_intent: OrderIntent
    risk_assessment_authorized: bool
    risk_authorization_id: str
    risk_authorization_status: str
    execution_state: OrderState
    fill_count: int
    fill_ids: list[str] = field(default_factory=list)
    ledger_balance_base: str = "0"
    ledger_balance_quote: str = "0"
    ledger_entry_count: int = 0
    outbox_event_id: str = ""
    redis_stream_entry_id: str = ""
    redis_consumed: bool = False
    inbox_delivered: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        """True if the full pipeline succeeded end-to-end."""
        return (
            self.risk_assessment_authorized
            and self.execution_state is OrderState.FILLED
            and self.fill_count >= 1
            and self.ledger_entry_count >= 1
            and self.redis_consumed
            and self.inbox_delivered
        )


class EndToEndSimulationScenario:
    """Orchestrates the end-to-end simulation: tenant → agent → Risk Kernel → ledger.

    Per Phase A scope: uses real PostgreSQL persistence (PersistentLedger,
    PersistentRiskKernel) and real Redis Streams event bus. All data is
    synthetic — the simulated exchange produces deterministic fills.

    Per Section 00.3: no live trading, no real credentials, no real
    exchange keys. The simulation exchange is used for execution.
    """

    CONSUMER_GROUP = "kti-simulation-group"
    CONSUMER_NAME = "kti-simulation-consumer"

    def __init__(
        self,
        *,
        ledger: PersistentLedger,
        kernel: PersistentRiskKernel,
        exchange: Any,
        redis_bus: RedisStreamBus,
    ) -> None:
        self._ledger = ledger
        self._kernel = kernel
        self._exchange = exchange
        self._redis_bus = redis_bus
        self._engine = ExecutionEngine(
            risk_kernel=kernel,
            exchange=exchange,
        )

    def setup_tenant(self, tenant_id: str, initial_usdt: str = "100000") -> None:
        """Provision a tenant with a risk policy and initial USDT balance."""
        # Register an active risk policy for the tenant
        policy = RiskPolicy.create(
            tenant_id=tenant_id,
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        self._kernel.register_policy(policy)

        # Fund the tenant's USDT account
        from contracts.ledger import AccountType

        with contextlib.suppress(Exception):
            # Account may already exist if called twice
            self._ledger.create_account(
                tenant_id=tenant_id,
                account_type=AccountType.SPOT,
                asset="USDT",
                initial_balance=initial_usdt,
            )

    def run(
        self,
        *,
        tenant_id: str,
        symbol: str = "BTC/USDT",
        side: str = "buy",
        quantity: str = "0.01",
        current_price: str = "50000.00",
    ) -> SimulationScenarioResult:
        """Run the full end-to-end simulation scenario.

        Returns a ``SimulationScenarioResult`` with the outcome of each stage.
        """
        result = SimulationScenarioResult(
            tenant_id=tenant_id,
            order_intent=OrderIntent.create(
                tenant_id=tenant_id,
                profile_id="sim-profile",
                symbol=symbol,
                side=side,
                quantity=quantity,
            ),
            risk_assessment_authorized=False,
            risk_authorization_id="",
            risk_authorization_status="",
            execution_state=OrderState.CREATED,
            fill_count=0,
        )

        # Ensure exchange is connected
        if not self._exchange.is_connected:
            self._exchange.connect()

        # Stage 1+2: Execute the order through the full pipeline
        # (ExecutionEngine calls kernel.authorize → reserve → submit →
        # consume internally; this is the real pipeline path)
        exec_result = self._engine.execute_order(
            result.order_intent,
            current_price=current_price,
        )
        result.execution_state = exec_result.state
        result.fill_count = len(exec_result.fills)
        result.fill_ids = [f.fill_id for f in exec_result.fills]

        # Read back the authorization that the engine created
        try:
            auth = self._kernel.get_authorization_for_intent(
                str(result.order_intent.intent_id)
            )
            result.risk_assessment_authorized = (
                auth.status is AuthorizationStatus.CONSUMED
                or auth.status is AuthorizationStatus.APPROVED
            )
            result.risk_authorization_id = str(auth.authorization_id)
            result.risk_authorization_status = auth.status.value
        except Exception as exc:
            result.risk_assessment_authorized = False
            result.risk_authorization_status = "not_found"
            result.errors.append(f"Could not read authorization: {exc}")

        if exec_result.state is not OrderState.FILLED:
            result.errors.append(
                f"Execution did not fill (state: {exec_result.state.value})"
            )
            # Still emit and relay the event for the scenario record

        # Stage 3: Record the fill in the persistent ledger
        for fill in exec_result.fills:
            self._ledger.record_fill(
                tenant_id=tenant_id,
                fill=fill,
                symbol=symbol,
            )

        # Check ledger state
        _SYMBOL_PAIR_LEN = 2
        parts = symbol.split("/")
        base_asset = parts[0] if len(parts) == _SYMBOL_PAIR_LEN else symbol
        quote_asset = parts[1] if len(parts) == _SYMBOL_PAIR_LEN else "USDT"
        result.ledger_balance_base = self._ledger.get_balance(tenant_id, base_asset)
        result.ledger_balance_quote = self._ledger.get_balance(tenant_id, quote_asset)
        result.ledger_entry_count = self._ledger.entry_count

        # Stage 4: Emit an event to the DB transactional outbox
        from uuid import uuid4

        outbox_event_id = str(uuid4())
        result.outbox_event_id = outbox_event_id
        fill_qty = (
            str(exec_result.fills[0].filled_quantity)
            if exec_result.fills
            else quantity
        )
        self._ledger.emit_outbox_event(
            event_id=outbox_event_id,
            aggregate_type="order",
            aggregate_id=str(result.order_intent.intent_id),
            event_type="order.filled",
            payload={
                "tenant_id": tenant_id,
                "symbol": symbol,
                "side": side,
                "quantity": fill_qty,
                "fill_count": len(exec_result.fills),
                "execution_state": exec_result.state.value,
            },
            tenant_id=tenant_id,
        )

        # Stage 5: Relay outbox events to Redis Streams
        relay_result = self._redis_bus.relay_outbox(self._ledger)
        if relay_result.errors:
            result.errors.extend(relay_result.errors)

        # Stage 6: Consume the event from Redis Streams
        consumed = self._redis_bus.consume(
            STREAM_ORDER_EVENTS,
            self.CONSUMER_GROUP,
            self.CONSUMER_NAME,
            count=10,
            block_ms=100,
        )
        # Find our event
        our_event: StreamEvent | None = None
        our_entry_id: str = ""
        for entry_id, stream_evt in consumed:
            if stream_evt.event_id == outbox_event_id:
                our_event = stream_evt
                our_entry_id = entry_id
                break

        if our_event is not None:
            result.redis_stream_entry_id = our_entry_id
            result.redis_consumed = True

            # Stage 7: Deliver to inbox (idempotent)
            delivered = self._ledger.receive_inbox_message(
                message_id=f"sim-{outbox_event_id}",
                source="redis-streams-bus",
                event_type="order.filled",
                payload=our_event.payload,
                tenant_id=tenant_id,
            )
            result.inbox_delivered = delivered

            # Ack the Redis stream message
            self._redis_bus.ack(
                STREAM_ORDER_EVENTS,
                self.CONSUMER_GROUP,
                our_entry_id,
            )

        return result
