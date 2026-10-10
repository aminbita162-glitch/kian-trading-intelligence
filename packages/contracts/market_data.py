"""Market-data contracts for Kian Trading Intelligence.

Per AD-021 (Shared Market Data): normalize, validate, and reuse eligible
public market data while isolating tenant-specific decisions and credentials.
Reject stale or invalid market data from live execution.

Per AD-003 (Hybrid Low-Token Intelligence): routine indicators and risk
calculations must not depend on LLM availability. All market-data processing
is deterministic.

Per Section 08.1: approved provider adapters; normalized schemas; timestamp
validation; freshness checks; duplicate detection; ordering controls;
reconnection behavior; historical storage; deterministic replay; data provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4


class MarketDataEventType(StrEnum):
    """Normalized market-data event types.

    All provider-specific data is converted to one of these types.
    """

    TICKER = "ticker"
    TRADE = "trade"
    ORDER_BOOK_SNAPSHOT = "order_book_snapshot"
    ORDER_BOOK_UPDATE = "order_book_update"
    CANDLE = "candle"
    DISCONNECTION = "disconnection"
    RECONNECTION = "reconnection"


class ProviderType(StrEnum):
    """Supported provider types.

    No exchange is automatically approved for live use (Section 05.5).
    """

    SIMULATED = "simulated"
    EXCHANGE = "exchange"
    AGGREGATOR = "aggregator"


class DataStatus(StrEnum):
    """Status of market data after validation."""

    FRESH = "fresh"
    STALE = "stale"
    INVALID = "invalid"
    DUPLICATE = "duplicate"


class Timeframe(StrEnum):
    """Standardized timeframes for candle/OHLCV data."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"


@dataclass(frozen=True)
class EventId:
    """Stable identity for a market-data event.

    Per Section 05.3: every event must have a stable identity for
    idempotency and duplicate detection.
    """

    value: UUID

    @classmethod
    def generate(cls) -> EventId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Symbol:
    """Normalized trading symbol.

    Per AD-021: symbols are normalized across providers.
    """

    base: str
    quote: str

    @property
    def pair(self) -> str:
        return f"{self.base}/{self.quote}"

    def __str__(self) -> str:
        return self.pair

    @classmethod
    def parse(cls, pair: str) -> Symbol:
        """Parse a pair string like 'BTC/USDT' into a Symbol."""
        if "/" not in pair:
            raise ValueError(f"Invalid symbol format: {pair!r}. Expected 'BASE/QUOTE'.")
        base, quote = pair.split("/", 1)
        base = base.strip().upper()
        quote = quote.strip().upper()
        if not base or not quote:
            raise ValueError(f"Invalid symbol format: {pair!r}. Empty base or quote.")
        return cls(base=base, quote=quote)


@dataclass(frozen=True)
class OrderBookLevel:
    """A single price level in an order book."""

    price: str  # String for exact decimal representation (AD-018)
    amount: str  # String for exact decimal representation

    def __post_init__(self) -> None:
        if float(self.price) <= 0:
            raise ValueError("Price must be positive.")
        if float(self.amount) < 0:
            raise ValueError("Amount must be non-negative.")


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Normalized order book snapshot.

    Per Section 08.1: normalized schemas with ordering controls.
    """

    symbol: Symbol
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    timestamp: datetime
    sequence: int

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Order book timestamp must be timezone-aware (UTC).")
        if self.sequence < 0:
            raise ValueError("Sequence must be non-negative.")


@dataclass(frozen=True)
class Trade:
    """Normalized trade event.

    Per Section 05.3: every trade must have a stable identity.
    """

    trade_id: str
    symbol: Symbol
    price: str
    amount: str
    side: str  # "buy" or "sell"
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid trade side: {self.side!r}. Must be 'buy' or 'sell'.")
        if float(self.price) <= 0:
            raise ValueError("Trade price must be positive.")
        if float(self.amount) <= 0:
            raise ValueError("Trade amount must be positive.")
        if self.timestamp.tzinfo is None:
            raise ValueError("Trade timestamp must be timezone-aware (UTC).")


@dataclass(frozen=True)
class Candle:
    """OHLCV candle for historical price data.

    Per AD-018: exact decimal arithmetic. Per AD-003: deterministic.
    """

    symbol: Symbol
    timeframe: Timeframe
    open: str
    high: str
    low: str
    close: str
    volume: str
    open_time: datetime
    close_time: datetime

    def __post_init__(self) -> None:
        if float(self.open) <= 0:
            raise ValueError("Candle open price must be positive.")
        if float(self.high) < float(self.open):
            raise ValueError("Candle high must be >= open.")
        if float(self.low) > float(self.open):
            raise ValueError("Candle low must be <= open.")
        if float(self.high) < float(self.low):
            raise ValueError("Candle high must be >= low.")
        if float(self.close) <= 0:
            raise ValueError("Candle close price must be positive.")
        if float(self.volume) < 0:
            raise ValueError("Candle volume must be non-negative.")
        if self.open_time.tzinfo is None:
            raise ValueError("Candle open_time must be timezone-aware (UTC).")
        if self.close_time.tzinfo is None:
            raise ValueError("Candle close_time must be timezone-aware (UTC).")


@dataclass
class Ticker:
    """Normalized ticker event.

    Per AD-021: normalized market data with timestamp validation.
    """

    symbol: Symbol
    last_price: str
    bid: str
    ask: str
    high_24h: str
    low_24h: str
    volume_24h: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if float(self.last_price) <= 0:
            raise ValueError("Ticker last_price must be positive.")
        if float(self.bid) <= 0:
            raise ValueError("Ticker bid must be positive.")
        if float(self.ask) <= 0:
            raise ValueError("Ticker ask must be positive.")
        if float(self.ask) < float(self.bid):
            raise ValueError("Ticker ask must be >= bid.")
        if float(self.volume_24h) < 0:
            raise ValueError("Ticker volume_24h must be non-negative.")
        if self.timestamp.tzinfo is None:
            raise ValueError("Ticker timestamp must be timezone-aware (UTC).")


@dataclass
class MarketDataEvent:
    """Normalized market-data event.

    Per Section 08.1: all provider data is normalized to this schema.
    Per Section 11.3: critical events include event identifier, event type,
    schema version, timestamp, and producer identity.

    Attributes:
        event_id: Stable unique identifier for the event.
        event_type: Normalized event type.
        symbol: Trading symbol.
        provider: Provider type that produced the event.
        timestamp: UTC timestamp of the event.
        received_at: UTC timestamp when the event was received.
        sequence: Provider sequence number for ordering (0 if N/A).
        payload: Event-specific data (Ticker, Trade, Candle, OrderBookSnapshot).
        provenance: Origin/traceability information (Section 08.1).
    """

    event_id: EventId
    event_type: MarketDataEventType
    symbol: Symbol
    provider: ProviderType
    timestamp: datetime
    received_at: datetime
    sequence: int = 0
    payload: Ticker | Trade | Candle | OrderBookSnapshot | None = None
    provenance: str = ""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Event timestamp must be timezone-aware (UTC).")
        if self.received_at.tzinfo is None:
            raise ValueError("Event received_at must be timezone-aware (UTC).")

    @property
    def age(self) -> timedelta:
        """Age of the event relative to now."""
        return datetime.now(UTC) - self.timestamp

    @property
    def latency(self) -> timedelta:
        """Processing latency: received_at - timestamp."""
        return self.received_at - self.timestamp


@dataclass
class FreshnessConfig:
    """Configuration for market-data freshness checks.

    Per Section 08.1: timestamp validation and freshness checks.
    Per AD-021: reject stale or invalid market data from live execution.

    Attributes:
        max_age: Maximum acceptable age for data to be considered fresh.
        warning_threshold: Age at which a warning is emitted (fraction of max_age).
    """

    max_age: timedelta = field(default_factory=lambda: timedelta(seconds=30))
    warning_threshold: float = 0.8

    def __post_init__(self) -> None:
        if self.max_age <= timedelta(0):
            raise ValueError("max_age must be positive.")
        if not 0 < self.warning_threshold <= 1.0:
            raise ValueError("warning_threshold must be in (0, 1.0].")

    def is_fresh(self, event: MarketDataEvent) -> bool:
        """Check if an event is fresh."""
        return event.age <= self.max_age

    def is_stale(self, event: MarketDataEvent) -> bool:
        """Check if an event is stale."""
        return event.age > self.max_age

    def is_warning(self, event: MarketDataEvent) -> bool:
        """Check if an event age is in the warning zone."""
        warning_age = self.max_age * self.warning_threshold
        return event.age > warning_age and not self.is_stale(event)
