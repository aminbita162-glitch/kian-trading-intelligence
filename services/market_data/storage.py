"""Historical storage and replay engine for market data.

Per Section 08.1: historical storage and deterministic replay.
Per AD-023 (Digital Twin): deterministic simulation, exchange emulation,
replay, fault injection, and repeatable verification.
Per AD-017 (Fault-Tolerant Infrastructure): recovery without duplicate
financial effects.

The storage layer persists market-data events for later retrieval.
The replay engine re-emits stored events in original order, deterministically.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from contracts.market_data import (
    MarketDataEvent,
    MarketDataEventType,
    Symbol,
)


@dataclass
class StorageRecord:
    """A stored market-data record.

    Per Addendum A03: durable, human-auditable evidence library.
    """

    record_id: int
    event: MarketDataEvent
    stored_at: datetime

    def __post_init__(self) -> None:
        if self.stored_at.tzinfo is None:
            raise ValueError("stored_at must be timezone-aware (UTC).")


class HistoricalStorage:
    """In-memory historical storage for market-data events.

    Per Section 08.1: historical storage with ordering controls.
    Per AD-017: services must recover without creating duplicate effects.

    Note: this is an in-memory implementation suitable for Phase 03
    (simulation, no live trading). Production requires PostgreSQL
    with durable persistence (planned, not yet implemented).
    """

    def __init__(self) -> None:
        self._records: list[StorageRecord] = []
        self._next_id: int = 1
        self._by_symbol: dict[str, list[int]] = {}
        self._by_type: dict[str, list[int]] = {}
        self._by_event_id: set[str] = set()

    def store(self, event: MarketDataEvent) -> StorageRecord:
        """Store a market-data event.

        Per Section 08.1: duplicate detection in historical storage.
        Returns the stored record.
        """
        event_key = str(event.event_id)
        if event_key in self._by_event_id:
            raise ValueError(f"Duplicate event stored: {event_key}")
        self._by_event_id.add(event_key)

        record = StorageRecord(
            record_id=self._next_id,
            event=event,
            stored_at=datetime.now(UTC),
        )
        self._next_id += 1

        self._records.append(record)
        self._by_symbol.setdefault(event.symbol.pair, []).append(record.record_id)
        self._by_type.setdefault(event.event_type.value, []).append(record.record_id)
        return record

    def retrieve_by_symbol(
        self,
        symbol: Symbol,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[StorageRecord]:
        """Retrieve records by symbol, optionally filtered by time range."""
        ids = self._by_symbol.get(symbol.pair, [])
        records = [r for r in self._records if r.record_id in ids]

        if start_time is not None:
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=UTC)
            records = [r for r in records if r.event.timestamp >= start_time]
        if end_time is not None:
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=UTC)
            records = [r for r in records if r.event.timestamp <= end_time]

        return sorted(records, key=lambda r: r.record_id)

    def retrieve_by_type(
        self,
        event_type: MarketDataEventType,
    ) -> list[StorageRecord]:
        """Retrieve all records of a given event type."""
        ids = self._by_type.get(event_type.value, [])
        return sorted(
            (r for r in self._records if r.record_id in ids),
            key=lambda r: r.record_id,
        )

    @property
    def count(self) -> int:
        """Total number of stored records."""
        return len(self._records)

    def clear(self) -> None:
        """Clear all stored records."""
        self._records.clear()
        self._by_symbol.clear()
        self._by_type.clear()
        self._by_event_id.clear()
        self._next_id = 1


@dataclass
class ReplayResult:
    """Result of a replay operation.

    Per AD-023: repeatable verification.
    """

    events_replayed: int
    start_time: datetime
    end_time: datetime
    symbols_replayed: list[str]
    duration: timedelta

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is None:
            raise ValueError("start_time must be timezone-aware (UTC).")
        if self.end_time.tzinfo is None:
            raise ValueError("end_time must be timezone-aware (UTC).")

    @property
    def events_per_second(self) -> float:
        """Replay throughput in events per second."""
        seconds = self.duration.total_seconds()
        if seconds == 0:
            return float(self.events_replayed)
        return self.events_replayed / seconds


class ReplayEngine:
    """Deterministic replay engine for stored market data.

    Per Section 08.1: deterministic replay.
    Per AD-023: replay, fault injection, and repeatable verification.

    The replay engine re-emits stored events in their original order,
    optionally filtered by symbol and time range. Replay is deterministic:
    the same stored events produce the same replay sequence every time.
    """

    def __init__(self, storage: HistoricalStorage) -> None:
        self._storage = storage

    def replay(
        self,
        *,
        symbol: Symbol | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        speed: float = 1.0,
    ) -> ReplayResult:
        """Replay stored events deterministically.

        Args:
            symbol: Optional symbol filter. If None, replays all symbols.
            start_time: Optional start time filter.
            end_time: Optional end time filter.
            speed: Replay speed multiplier (1.0 = real-time, 2.0 = 2x speed).
                Currently informational — replay is instant (no delay).

        Returns:
            ReplayResult with replay statistics.
        """
        if speed <= 0:
            raise ValueError("speed must be positive.")

        if symbol is not None:
            records = self._storage.retrieve_by_symbol(symbol, start_time, end_time)
        else:
            records = self._storage.retrieve_by_type(MarketDataEventType.TRADE)
            if not records:
                records = self._storage.retrieve_by_type(MarketDataEventType.TICKER)
            records = sorted(records, key=lambda r: r.event.timestamp)
            if start_time is not None:
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=UTC)
                records = [r for r in records if r.event.timestamp >= start_time]
            if end_time is not None:
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=UTC)
                records = [r for r in records if r.event.timestamp <= end_time]

        # Deterministic: events are replayed in timestamp order
        sorted_records = sorted(records, key=lambda r: r.event.timestamp)

        symbols_seen: set[str] = set()
        for record in sorted_records:
            symbols_seen.add(record.event.symbol.pair)

        start_dt = datetime.now(UTC)
        # Replay is instant — no artificial delay
        events_replayed = len(sorted_records)
        end_dt = datetime.now(UTC)

        return ReplayResult(
            events_replayed=events_replayed,
            start_time=start_dt,
            end_time=end_dt,
            symbols_replayed=sorted(symbols_seen),
            duration=end_dt - start_dt,
        )

    def replay_iterator(
        self,
        *,
        symbol: Symbol | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Iterator[MarketDataEvent]:
        """Iterate over stored events in replay order.

        Yields events deterministically by timestamp order.
        """
        if symbol is not None:
            records = self._storage.retrieve_by_symbol(symbol, start_time, end_time)
        else:
            records = []
            for et in MarketDataEventType:
                records.extend(self._storage.retrieve_by_type(et))
            records = sorted(records, key=lambda r: r.event.timestamp)
            if start_time is not None:
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=UTC)
                records = [r for r in records if r.event.timestamp >= start_time]
            if end_time is not None:
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=UTC)
                records = [r for r in records if r.event.timestamp <= end_time]

        for record in sorted(records, key=lambda r: r.event.timestamp):
            yield record.event
