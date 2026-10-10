"""Market-data event processing and validation pipeline.

Per Section 08.1: timestamp validation, freshness checks, duplicate detection,
ordering controls, reconnection behavior, normalized events.
Per AD-021: reject stale or invalid market data from live execution.
Per AD-003: all processing is deterministic — no LLM dependency.

The processor validates, deduplicates, freshness-checks, and normalizes
incoming market-data events before they reach downstream consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from contracts.market_data import (
    DataStatus,
    FreshnessConfig,
    MarketDataEvent,
)
from services.market_data.storage import HistoricalStorage


@dataclass
class ProcessingResult:
    """Result of processing a market-data event.

    Attributes:
        accepted: Whether the event was accepted for downstream processing.
        status: Data status after freshness/duplicate checks.
        event: The processed event (None if rejected).
        reject_reason: Reason for rejection if not accepted.
        processed_at: UTC timestamp of processing.
    """

    accepted: bool
    status: DataStatus
    event: MarketDataEvent | None
    reject_reason: str | None
    processed_at: datetime

    def __post_init__(self) -> None:
        if self.processed_at.tzinfo is None:
            raise ValueError("processed_at must be timezone-aware (UTC).")


@dataclass
class ProcessingStats:
    """Aggregate statistics for event processing."""

    total: int = 0
    accepted: int = 0
    stale: int = 0
    duplicate: int = 0
    invalid: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_symbol: dict[str, int] = field(default_factory=dict)

    def record_accepted(self, event: MarketDataEvent) -> None:
        self.total += 1
        self.accepted += 1
        self.by_type[event.event_type.value] = self.by_type.get(event.event_type.value, 0) + 1
        self.by_symbol[event.symbol.pair] = self.by_symbol.get(event.symbol.pair, 0) + 1

    def record_rejected(self, status: DataStatus, event: MarketDataEvent | None) -> None:
        self.total += 1
        if status is DataStatus.STALE:
            self.stale += 1
        elif status is DataStatus.DUPLICATE:
            self.duplicate += 1
        elif status is DataStatus.INVALID:
            self.invalid += 1
        if event is not None:
            self.by_type[event.event_type.value] = self.by_type.get(event.event_type.value, 0) + 1
            self.by_symbol[event.symbol.pair] = self.by_symbol.get(event.symbol.pair, 0) + 1


class EventProcessor:
    """Market-data event processor with validation, freshness, and dedup.

    Per Section 08.1: the processor pipeline handles:
    1. Timestamp validation (timezone-aware UTC)
    2. Freshness checks (reject stale data per AD-021)
    3. Duplicate detection (per event ID)
    4. Ordering controls (sequence numbers)
    5. Normalization (convert to MarketDataEvent)
    6. Storage (persist to historical storage)

    Per AD-003: all processing is deterministic.
    """

    def __init__(
        self,
        *,
        freshness: FreshnessConfig | None = None,
        storage: HistoricalStorage | None = None,
        max_future_seconds: float = 5.0,
    ) -> None:
        self.freshness = freshness or FreshnessConfig()
        self.storage = storage or HistoricalStorage()
        self.max_future_seconds = max_future_seconds
        self._seen_event_ids: set[str] = set()
        self._last_sequence: dict[str, int] = {}
        self.stats = ProcessingStats()

    def process(self, event: MarketDataEvent) -> ProcessingResult:
        """Process a single market-data event.

        Returns a ProcessingResult indicating whether the event was accepted.
        Per AD-021: stale data is rejected from live execution.
        Per Section 08.1: duplicate detection and ordering controls.
        """
        now = datetime.now(UTC)
        processed_at = now

        # 1. Timestamp validation
        if event.timestamp.tzinfo is None:
            self.stats.record_rejected(DataStatus.INVALID, event)
            return ProcessingResult(
                accepted=False,
                status=DataStatus.INVALID,
                event=None,
                reject_reason="Timestamp must be timezone-aware (UTC).",
                processed_at=processed_at,
            )

        # 2. Future timestamp check (clock skew tolerance)
        max_future = now + timedelta(seconds=self.max_future_seconds)
        if event.timestamp > max_future:
            self.stats.record_rejected(DataStatus.INVALID, event)
            return ProcessingResult(
                accepted=False,
                status=DataStatus.INVALID,
                event=None,
                reject_reason=f"Event timestamp is in the future: {event.timestamp.isoformat()}",
                processed_at=processed_at,
            )

        # 3. Duplicate detection
        event_key = str(event.event_id)
        if event_key in self._seen_event_ids:
            self.stats.record_rejected(DataStatus.DUPLICATE, event)
            return ProcessingResult(
                accepted=False,
                status=DataStatus.DUPLICATE,
                event=None,
                reject_reason=f"Duplicate event ID: {event_key}",
                processed_at=processed_at,
            )
        self._seen_event_ids.add(event_key)

        # 4. Ordering control (sequence numbers)
        if event.sequence > 0:
            sym_key = event.symbol.pair
            last_seq = self._last_sequence.get(sym_key, 0)
            if event.sequence <= last_seq:
                self.stats.record_rejected(DataStatus.INVALID, event)
                return ProcessingResult(
                    accepted=False,
                    status=DataStatus.INVALID,
                    event=None,
                    reject_reason=(
                        f"Sequence out of order: {event.sequence} <= {last_seq} for {sym_key}"
                    ),
                    processed_at=processed_at,
                )
            self._last_sequence[sym_key] = event.sequence

        # 5. Freshness check
        if self.freshness.is_stale(event):
            self.stats.record_rejected(DataStatus.STALE, event)
            return ProcessingResult(
                accepted=False,
                status=DataStatus.STALE,
                event=None,
                reject_reason=(f"Stale event: age={event.age} > max_age={self.freshness.max_age}"),
                processed_at=processed_at,
            )

        # 6. Store and accept
        self.storage.store(event)
        self.stats.record_accepted(event)

        return ProcessingResult(
            accepted=True,
            status=DataStatus.FRESH,
            event=event,
            reject_reason=None,
            processed_at=processed_at,
        )

    def reset(self) -> None:
        """Reset processor state (for testing)."""
        self._seen_event_ids.clear()
        self._last_sequence.clear()
        self.stats = ProcessingStats()
        self.storage.clear()
