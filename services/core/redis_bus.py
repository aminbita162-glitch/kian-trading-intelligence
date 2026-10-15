"""Redis Streams event bus — Phase A: Real Infrastructure.

Per DIRECTIV.txt V1.4 Phase A: "Activate Redis Streams as the
operational event bus with transactional outbox/inbox."

This module provides ``RedisStreamBus``, a real Redis Streams-backed
event bus that bridges the existing transactional outbox/inbox pattern
(in ``PersistentLedger``) to Redis Streams for operational event delivery.

Architecture:
  1. Domain services write events to the DB-backed transactional
     outbox (``PersistentLedger.emit_outbox_event``) within the same
     DB transaction as the state change.
  2. A relay (``RedisStreamBus.relay_outbox``) polls the outbox,
     publishes each event to a Redis Stream, and marks it processed.
  3. Consumers read from the Redis Stream via consumer groups
     (``RedisStreamBus.consume``), process the event, and ack.
  4. The inbox on the receiving side provides idempotent deduplication
     (``PersistentLedger.receive_inbox_message``).

Per AD-031 (PostgreSQL for durable records): the DB outbox remains the
source of truth; Redis Streams provide the operational transport.

Per Section 00.3: no live trading, no real credentials, no real exchange
keys. All data is synthetic. Redis is used only for simulation event
delivery — never for live market data or live order execution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.ledger.persistent_ledger import PersistentLedger

logger = logging.getLogger(__name__)

# ── Stream names ──

STREAM_ORDER_EVENTS = "kti:order-events"
STREAM_RISK_EVENTS = "kti:risk-events"
STREAM_LEDGER_EVENTS = "kti:ledger-events"

DEFAULT_STREAM_MAXLEN = 10_000


@dataclass
class StreamEvent:
    """A single event published to or consumed from a Redis Stream."""

    event_id: str
    stream: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    tenant_id: str

    def to_fields(self) -> dict[str, str]:
        """Serialize to Redis stream fields (all string values)."""
        return {
            "event_id": self.event_id,
            "stream": self.stream,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "payload": json.dumps(self.payload),
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_fields(cls, fields: dict[str | bytes, str | bytes]) -> StreamEvent:
        """Deserialize from Redis stream fields (decode bytes if needed)."""
        def _s(v: str | bytes) -> str:
            return v.decode() if isinstance(v, bytes) else v

        return cls(
            event_id=_s(fields["event_id"]),
            stream=_s(fields["stream"]),
            aggregate_type=_s(fields["aggregate_type"]),
            aggregate_id=_s(fields["aggregate_id"]),
            event_type=_s(fields["event_type"]),
            payload=json.loads(_s(fields["payload"])),
            tenant_id=_s(fields["tenant_id"]),
        )


@dataclass
class RelayResult:
    """Result of a relay poll cycle."""

    relayed: int = 0
    remaining: int = 0
    errors: list[str] = field(default_factory=list)


class RedisStreamBus:
    """Redis Streams-backed event bus for operational event delivery.

    Wraps a ``redis.Redis`` client and provides:
    - ``publish``: add an event to a Redis Stream.
    - ``relay_outbox``: poll the DB transactional outbox, publish pending
      events to Redis Streams, and mark them processed.
    - ``consume``: read events from a Redis Stream via consumer groups.
    - ``ack``: acknowledge a processed event.

    Per Phase A scope: this is the operational event bus connecting the
    agent → Risk Kernel → ledger pipeline. All data is synthetic.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        maxlen: int = DEFAULT_STREAM_MAXLEN,
    ) -> None:
        """Initialize with an existing redis-py client.

        Args:
            redis_client: A connected ``redis.Redis`` instance.
            maxlen: Maximum stream length (approximate trimming).
        """
        self._redis = redis_client
        self._maxlen = maxlen
        self._consumer_groups_created: set[str] = set()

    def _ensure_consumer_group(self, stream: str, group: str) -> None:
        """Create the consumer group if it doesn't exist."""
        key = f"{stream}:{group}"
        if key in self._consumer_groups_created:
            return
        try:
            self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception as exc:
            # BUSYGROUP — group already exists
            if "BUSYGROUP" not in str(exc):
                raise
        self._consumer_groups_created.add(key)

    def publish(self, stream: str, event: StreamEvent) -> str:
        """Publish an event to a Redis Stream.

        Returns the Redis Stream entry ID.
        """
        entry_id = self._redis.xadd(
            stream,
            event.to_fields(),
            maxlen=self._maxlen,
            approximate=True,
        )
        # redis-py returns bytes when decode_responses=False
        if isinstance(entry_id, bytes):
            entry_id = entry_id.decode()
        return entry_id

    def relay_outbox(
        self,
        ledger: PersistentLedger,
        *,
        batch_size: int = 100,
    ) -> RelayResult:
        """Relay pending outbox events from the DB to Redis Streams.

        Polls the transactional outbox in ``ledger``, publishes each
        pending event to the appropriate Redis Stream, and marks it
        processed in the DB. This bridges the DB transactional outbox
        to the Redis Streams operational bus.

        Per Phase A: this is the "Activate Redis Streams as the
        operational event bus with transactional outbox/inbox" scope.
        """
        result = RelayResult()
        pending = ledger.get_pending_outbox_events(limit=batch_size)
        result.remaining = len(pending)

        for evt in pending:
            stream = self._stream_for_event(evt["event_type"])
            stream_event = StreamEvent(
                event_id=evt["event_id"],
                stream=stream,
                aggregate_type=evt["aggregate_type"],
                aggregate_id=evt["aggregate_id"],
                event_type=evt["event_type"],
                payload=evt["payload"],
                tenant_id=evt["tenant_id"],
            )
            try:
                self.publish(stream, stream_event)
                ledger.mark_outbox_processed(evt["event_id"])
                result.relayed += 1
            except Exception as exc:
                result.errors.append(
                    f"Failed to relay event {evt['event_id']}: {exc}"
                )
                logger.error("Relay error for event %s: %s", evt["event_id"], exc)

        result.remaining = max(0, result.remaining - result.relayed)
        return result

    def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_ms: int = 0,
    ) -> list[tuple[str, StreamEvent]]:
        """Consume events from a Redis Stream via consumer group.

        Returns a list of (entry_id, StreamEvent) tuples.
        """
        self._ensure_consumer_group(stream, group)
        raw = self._redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )
        events: list[tuple[str, StreamEvent]] = []
        for _stream_name, entries in raw:
            for entry_id, fields in entries:
                if isinstance(entry_id, bytes):
                    entry_id = entry_id.decode()
                events.append((entry_id, StreamEvent.from_fields(fields)))
        return events

    def ack(self, stream: str, group: str, entry_id: str) -> None:
        """Acknowledge a processed event."""
        self._redis.xack(stream, group, entry_id)

    def pending(self, stream: str, group: str) -> int:
        """Return the count of pending (un-acked) messages in the group."""
        info = self._redis.xpending(stream, group)
        if isinstance(info, dict):
            return int(info.get("pending", 0))
        # Older redis-py returns a list: [pending_count, ...]
        return int(info[0]) if info else 0

    def stream_length(self, stream: str) -> int:
        """Return the number of entries in a stream."""
        return int(self._redis.xlen(stream))

    @staticmethod
    def _stream_for_event(event_type: str) -> str:
        """Map an event_type to the appropriate Redis Stream name."""
        if event_type.startswith("order"):
            return STREAM_ORDER_EVENTS
        if event_type.startswith("risk"):
            return STREAM_RISK_EVENTS
        if event_type.startswith("ledger") or event_type.startswith("fill"):
            return STREAM_LEDGER_EVENTS
        return STREAM_ORDER_EVENTS  # default


def create_redis_client(
    url: str = "redis://localhost:6379",
    *,
    decode_responses: bool = False,
) -> Any:
    """Create a redis-py client from a URL.

    Per Section 00.3: no real credentials or production secrets.
    The URL points to a local/test Redis instance only.
    """
    import redis as redis_lib

    return redis_lib.Redis.from_url(url, decode_responses=decode_responses)
