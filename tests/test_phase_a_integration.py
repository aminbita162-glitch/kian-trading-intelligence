"""Phase A — Real Infrastructure integration tests.

Per DIRECTIV.txt V1.4 Phase A acceptance criteria:
- "Integration tests against real PostgreSQL and Redis pass."
- "The end-to-end simulation scenario succeeds and is recorded in
   test-house/phase-a/evidence.md."
- "No LIVE capability is enabled."

These tests spin up real PostgreSQL and Redis containers via
testcontainers, wire PersistentLedger and PersistentRiskKernel to the
real PostgreSQL, activate the Redis Streams event bus, and run the
full end-to-end simulation scenario.

Skipped if Docker, testcontainers, psycopg2, or redis is not available.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from decimal import Decimal
from importlib.util import find_spec
from subprocess import run
from typing import Any

import pytest

from contracts.enums import OrderState
from contracts.risk import AuthorizationStatus, RiskPolicyStatus

# Skip if Docker, testcontainers, psycopg2, or redis is not available
try:
    from testcontainers.postgres import PostgresContainer
except ImportError:
    PostgresContainer = None  # type: ignore[assignment,misc]

try:
    from testcontainers.redis import RedisContainer
except ImportError:
    RedisContainer = None  # type: ignore[assignment,misc]


def _docker_daemon_running() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        run(  # noqa: S603,S607 — trusted local binary
            ["docker", "info"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


psycopg2_available = find_spec("psycopg2") is not None
redis_available = find_spec("redis") is not None
docker_available = _docker_daemon_running()
pytestmark = pytest.mark.skipif(
    not docker_available
    or PostgresContainer is None
    or RedisContainer is None
    or not psycopg2_available
    or not redis_available,
    reason="Docker daemon, testcontainers, psycopg2, or redis not available",
)


# ── Fixtures ──


@pytest.fixture
def pg_container() -> Iterator[Any]:
    """Start a real PostgreSQL container."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
def redis_container() -> Iterator[Any]:
    """Start a real Redis container."""
    with RedisContainer("redis:7-alpine") as rd:
        yield rd


@pytest.fixture
def pg_ledger(pg_container: Any) -> Iterator[Any]:
    """PersistentLedger connected to real PostgreSQL."""
    from services.ledger.persistent_ledger import PersistentLedger

    url = pg_container.get_connection_url()
    ledger = PersistentLedger(db_url=url)
    yield ledger
    ledger.close()


@pytest.fixture
def pg_kernel(pg_container: Any) -> Iterator[Any]:
    """PersistentRiskKernel connected to real PostgreSQL."""
    from services.risk_kernel.persistent_kernel import PersistentRiskKernel

    url = pg_container.get_connection_url()
    kern = PersistentRiskKernel(db_url=url)
    yield kern
    kern.close()


@pytest.fixture
def redis_bus_client(redis_container: Any) -> Iterator[Any]:
    """RedisStreamBus connected to real Redis."""
    from services.core.redis_bus import RedisStreamBus

    import redis as redis_lib

    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    url = f"redis://{host}:{port}"
    client = redis_lib.Redis.from_url(url, decode_responses=True)
    bus = RedisStreamBus(client)
    yield bus
    client.flushall()
    client.close()


@pytest.fixture
def sim_exchange() -> Iterator[Any]:
    """Connected simulated exchange (deterministic fills)."""
    from simulation.exchange_simulator import ExchangeSimulator

    exchange = ExchangeSimulator()
    exchange.connect()
    yield exchange
    # ExchangeSimulator has no disconnect; nothing to clean up


# ── Tests: PostgreSQL integration (Phase A) ──


class TestPostgreSQLIntegration:
    """Verify that PersistentLedger and PersistentRiskKernel work against
    real PostgreSQL — the foundation for Phase A real infrastructure."""

    def test_ledger_persists_fill_postgres(self, pg_ledger: Any) -> None:
        """A fill recorded against PostgreSQL survives and updates balances."""
        from contracts.exchange import ClientOrderId, FillResult
        from contracts.ledger import AccountType
        from datetime import UTC, datetime

        pg_ledger.create_account(
            tenant_id="tenant-a",
            account_type=AccountType.SPOT,
            asset="USDT",
            initial_balance="100000",
        )
        fill = FillResult(
            fill_id="fill-a-1",
            client_order_id=ClientOrderId("order-a-1"),
            symbol="BTC/USDT",
            side="buy",
            filled_quantity="0.01",
            fill_price="50000.00",
            fee="5.00",
            timestamp=datetime.now(UTC),
        )
        pg_ledger.record_fill(tenant_id="tenant-a", fill=fill, symbol="BTC/USDT")

        btc_balance = pg_ledger.get_balance("tenant-a", "BTC")
        assert Decimal(btc_balance) > 0, "BTC balance must be positive after buy fill"
        usdt_balance = pg_ledger.get_balance("tenant-a", "USDT")
        assert Decimal(usdt_balance) < 100000, "USDT balance must decrease after buy"
        assert pg_ledger.entry_count >= 1

    def test_risk_kernel_authorize_postgres(self, pg_kernel: Any) -> None:
        """Risk kernel assesses and authorizes against real PostgreSQL."""
        from contracts.order import OrderIntent
        from contracts.risk import RiskPolicy

        policy = RiskPolicy.create(
            tenant_id="tenant-risk",
            max_concentration_pct="100.0",
            max_position_per_symbol=10000,
        ).activate()
        pg_kernel.register_policy(policy)

        active = pg_kernel.get_active_policy("tenant-risk")
        assert active.status is RiskPolicyStatus.ACTIVE

        intent = OrderIntent.create(
            tenant_id="tenant-risk",
            profile_id="p1",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.001",
        )
        auth = pg_kernel.authorize(intent, current_price="50000.00")
        assert auth.status is AuthorizationStatus.APPROVED

    def test_outbox_emit_relay_consume_postgres(
        self, pg_ledger: Any, redis_bus_client: Any
    ) -> None:
        """Outbox events are relayed to Redis and consumed back."""
        from uuid import uuid4

        event_id = str(uuid4())
        pg_ledger.emit_outbox_event(
            event_id=event_id,
            aggregate_type="test",
            aggregate_id="agg-1",
            event_type="order.filled",
            payload={"key": "value"},
            tenant_id="tenant-outbox",
        )

        # Relay to Redis
        relay = redis_bus_client.relay_outbox(pg_ledger)
        assert relay.relayed >= 1
        assert relay.remaining == 0

        # Consume from Redis
        events = redis_bus_client.consume(
            "kti:order-events",
            "test-group",
            "test-consumer",
            count=10,
            block_ms=100,
        )
        found = [e for _eid, e in events if e.event_id == event_id]
        assert len(found) == 1, "Event must be consumable from Redis Stream"

    def test_inbox_idempotent_postgres(self, pg_ledger: Any) -> None:
        """Inbox deduplication works on PostgreSQL."""
        r1 = pg_ledger.receive_inbox_message(
            message_id="msg-idem-1",
            source="redis-streams-bus",
            event_type="order.filled",
            payload={"x": 1},
            tenant_id="t1",
        )
        assert r1 is True, "First delivery must be accepted"
        r2 = pg_ledger.receive_inbox_message(
            message_id="msg-idem-1",
            source="redis-streams-bus",
            event_type="order.filled",
            payload={"x": 1},
            tenant_id="t1",
        )
        assert r2 is False, "Duplicate delivery must be rejected"


# ── Tests: Redis Streams integration ──


class TestRedisStreamsIntegration:
    """Verify that the Redis Streams event bus works against real Redis."""

    def test_publish_and_consume(self, redis_bus_client: Any) -> None:
        """Publish an event and consume it back from a Redis Stream."""
        from services.core.redis_bus import STREAM_ORDER_EVENTS, StreamEvent

        event = StreamEvent(
            event_id="evt-test-1",
            stream=STREAM_ORDER_EVENTS,
            aggregate_type="order",
            aggregate_id="agg-1",
            event_type="order.created",
            payload={"symbol": "BTC/USDT", "side": "buy"},
            tenant_id="tenant-1",
        )
        entry_id = redis_bus_client.publish(STREAM_ORDER_EVENTS, event)
        assert entry_id, "Redis must return a stream entry ID"

        events = redis_bus_client.consume(
            STREAM_ORDER_EVENTS,
            "test-int-group",
            "test-int-consumer",
            count=10,
            block_ms=100,
        )
        found = [e for _eid, e in events if e.event_id == "evt-test-1"]
        assert len(found) == 1, "Published event must be consumable"
        assert found[0].payload["symbol"] == "BTC/USDT"

    def test_ack_removes_from_pending(self, redis_bus_client: Any) -> None:
        """Acknowledging a message removes it from the pending list."""
        from services.core.redis_bus import STREAM_RISK_EVENTS, StreamEvent

        event = StreamEvent(
            event_id="evt-ack-1",
            stream=STREAM_RISK_EVENTS,
            aggregate_type="risk",
            aggregate_id="risk-1",
            event_type="risk.authorized",
            payload={"tenant": "t1"},
            tenant_id="t1",
        )
        redis_bus_client.publish(STREAM_RISK_EVENTS, event)
        events = redis_bus_client.consume(
            STREAM_RISK_EVENTS,
            "ack-test-group",
            "ack-test-consumer",
            count=10,
            block_ms=100,
        )
        assert len(events) == 1
        entry_id, _ = events[0]
        assert redis_bus_client.pending(STREAM_RISK_EVENTS, "ack-test-group") >= 1
        redis_bus_client.ack(STREAM_RISK_EVENTS, "ack-test-group", entry_id)
        assert redis_bus_client.pending(STREAM_RISK_EVENTS, "ack-test-group") == 0

    def test_stream_length_grows(self, redis_bus_client: Any) -> None:
        """Stream length grows with published events."""
        from services.core.redis_bus import STREAM_LEDGER_EVENTS, StreamEvent

        initial = redis_bus_client.stream_length(STREAM_LEDGER_EVENTS)
        event = StreamEvent(
            event_id="evt-len-1",
            stream=STREAM_LEDGER_EVENTS,
            aggregate_type="ledger",
            aggregate_id="ledger-1",
            event_type="ledger.entry_posted",
            payload={"x": 1},
            tenant_id="t1",
        )
        redis_bus_client.publish(STREAM_LEDGER_EVENTS, event)
        after = redis_bus_client.stream_length(STREAM_LEDGER_EVENTS)
        assert after == initial + 1


# ── Tests: End-to-end simulation scenario ──


class TestEndToEndSimulationScenario:
    """The Phase A end-to-end simulation scenario: tenant → agent →
    Risk Kernel → ledger with real PostgreSQL and Redis Streams."""

    def test_full_pipeline_succeeds(
        self,
        pg_ledger: Any,
        pg_kernel: Any,
        redis_bus_client: Any,
        sim_exchange: Any,
    ) -> None:
        """Full pipeline: order → risk → execute → ledger → outbox → Redis → inbox."""
        from services.core.e2e_simulation import EndToEndSimulationScenario

        scenario = EndToEndSimulationScenario(
            ledger=pg_ledger,
            kernel=pg_kernel,
            exchange=sim_exchange,
            redis_bus=redis_bus_client,
        )
        scenario.setup_tenant("tenant-e2e", initial_usdt="100000")

        result = scenario.run(
            tenant_id="tenant-e2e",
            symbol="BTC/USDT",
            side="buy",
            quantity="0.01",
            current_price="50000.00",
        )

        assert result.risk_assessment_authorized, (
            f"Risk must authorize: {result.errors}"
        )
        assert result.execution_state is OrderState.FILLED, (
            f"Execution must fill: state={result.execution_state}, errors={result.errors}"
        )
        assert result.fill_count >= 1, "Must have at least one fill"
        assert result.ledger_entry_count >= 1, "Ledger must have journal entries"
        assert result.redis_consumed, "Event must be consumed from Redis Stream"
        assert result.inbox_delivered, "Event must be delivered to inbox"
        assert result.succeeded, "Full end-to-end scenario must succeed"

    def test_data_persists_after_recreation(
        self,
        pg_container: Any,
        redis_bus_client: Any,
        sim_exchange: Any,
    ) -> None:
        """Data persists in PostgreSQL across ledger/kernel recreation."""
        from services.core.e2e_simulation import EndToEndSimulationScenario
        from services.ledger.persistent_ledger import PersistentLedger
        from services.risk_kernel.persistent_kernel import PersistentRiskKernel

        url = pg_container.get_connection_url()

        # First instance — run scenario
        ledger1 = PersistentLedger(db_url=url)
        kernel1 = PersistentRiskKernel(db_url=url)
        scenario = EndToEndSimulationScenario(
            ledger=ledger1,
            kernel=kernel1,
            exchange=sim_exchange,
            redis_bus=redis_bus_client,
        )
        scenario.setup_tenant("tenant-persist", initial_usdt="100000")
        result1 = scenario.run(
            tenant_id="tenant-persist",
            quantity="0.01",
            current_price="50000.00",
        )
        assert result1.succeeded
        balance1 = ledger1.get_balance("tenant-persist", "BTC")
        ledger1.close()
        kernel1.close()

        # Second instance — verify data survived
        ledger2 = PersistentLedger(db_url=url)
        balance2 = ledger2.get_balance("tenant-persist", "BTC")
        assert balance1 == balance2, "Balance must persist across recreation"
        assert ledger2.entry_count >= 1, "Journal entries must persist"
        ledger2.close()
