"""Provider adapter interfaces for market data.

Per AD-005 (Multi-Provider Financial Connectivity): use approved provider
adapters for exchange, wallet, and relevant financial connections.
Per Section 05.5: each approved adapter must define supported products
and operations; authentication scopes; order submission and cancellation;
order status and partial fills; rate limits; recovery and reconciliation
behavior; provider restrictions. No exchange is automatically approved.

Per Section 08.1: approved provider adapters with normalized schemas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from contracts.market_data import (
    Candle,
    DataStatus,
    EventId,
    FreshnessConfig,
    MarketDataEvent,
    MarketDataEventType,
    OrderBookSnapshot,
    ProviderType,
    Symbol,
    Ticker,
    Timeframe,
    Trade,
)


@dataclass
class ProviderConnectionState:
    """State of a provider adapter connection.

    Per Section 08.1: reconnection behavior.
    """

    connected: bool = False
    last_connected: datetime | None = None
    last_disconnected: datetime | None = None
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 5
    base_reconnect_delay: float = 1.0
    last_error: str | None = None

    def connect(self) -> None:
        """Mark the connection as established."""
        self.connected = True
        self.last_connected = datetime.now(UTC)
        self.reconnect_attempts = 0
        self.last_error = None

    def disconnect(self, reason: str = "") -> None:
        """Mark the connection as lost."""
        self.connected = False
        self.last_disconnected = datetime.now(UTC)
        self.last_error = reason or "Disconnected"

    def should_reconnect(self) -> bool:
        """Whether a reconnect attempt should be made."""
        return not self.connected and self.reconnect_attempts < self.max_reconnect_attempts

    def next_reconnect_delay(self) -> float:
        """Calculate exponential backoff delay for the next reconnect attempt."""
        exponent = self.reconnect_attempts
        delay = self.base_reconnect_delay * (2**exponent)
        self.reconnect_attempts += 1
        return float(delay)

    def reset(self) -> None:
        """Reset the connection state."""
        self.connected = False
        self.last_connected = None
        self.last_disconnected = None
        self.reconnect_attempts = 0
        self.last_error = None


@dataclass
class RateLimitState:
    """Rate-limit tracking for a provider adapter.

    Per Section 08.1: rate-limit handling.
    Per AD-025 (Cost-Aware Orchestration): rate limits and infrastructure
    cost controls without weakening safety.

    Attributes:
        max_requests_per_minute: Maximum requests per minute.
        current_minute: Timestamp tracking the current minute window.
        request_count: Requests made in the current minute.
    """

    max_requests_per_minute: int = 60
    current_minute: datetime = field(default_factory=lambda: datetime.now(UTC))
    request_count: int = 0

    def check(self) -> bool:
        """Check if a request can be made. Returns True if allowed."""
        now = datetime.now(UTC)
        elapsed = now - self.current_minute
        if elapsed >= timedelta(minutes=1):
            self.current_minute = now
            self.request_count = 0
        if self.request_count >= self.max_requests_per_minute:
            return False
        self.request_count += 1
        return True

    def remaining(self) -> int:
        """Return remaining requests in the current window."""
        now = datetime.now(UTC)
        elapsed = now - self.current_minute
        if elapsed >= timedelta(minutes=1):
            return self.max_requests_per_minute
        return self.max_requests_per_minute - self.request_count


class MarketDataProviderError(Exception):
    """Base exception for market-data provider errors."""


class ProviderDisconnectedError(MarketDataProviderError):
    """Raised when an operation is attempted on a disconnected provider."""


class RateLimitExceededError(MarketDataProviderError):
    """Raised when the provider rate limit is exceeded."""


class StaleDataError(MarketDataProviderError):
    """Raised when data is stale beyond the freshness threshold.

    Per AD-021: reject stale or invalid market data from live execution.
    """


class DuplicateEventError(MarketDataProviderError):
    """Raised when a duplicate event is detected.

    Per Section 08.1: duplicate detection.
    """


class MarketDataProvider(ABC):
    """Abstract base class for market-data provider adapters.

    Per AD-005: approved provider adapters for exchange connections.
    Per Section 08.1: approved provider adapters with normalized schemas.

    Concrete providers must implement:
    - connect()/disconnect() for connection lifecycle (Section 08.1)
    - get_ticker() for current ticker data
    - get_order_book() for order book snapshots
    - get_candles() for historical OHLCV data
    - stream_trades() for streaming trade events (reconnection behavior)
    """

    def __init__(
        self,
        *,
        provider_type: ProviderType,
        freshness: FreshnessConfig | None = None,
        max_rate_per_minute: int = 60,
    ) -> None:
        self.provider_type = provider_type
        self.freshness = freshness or FreshnessConfig()
        self.connection = ProviderConnectionState()
        self.rate_limiter = RateLimitState(max_requests_per_minute=max_rate_per_minute)
        self._seen_event_ids: set[str] = set()
        self._last_sequence: dict[str, int] = {}

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the provider."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the provider connection."""

    @abstractmethod
    async def get_ticker(self, symbol: Symbol) -> Ticker:
        """Get the current ticker for a symbol."""

    @abstractmethod
    async def get_order_book(self, symbol: Symbol, depth: int = 10) -> OrderBookSnapshot:
        """Get the current order book snapshot for a symbol."""

    @abstractmethod
    async def get_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> list[Candle]:
        """Get historical candles for a symbol."""

    @abstractmethod
    def stream_trades(self, symbol: Symbol) -> AsyncIterator[Trade]:
        """Stream trades for a symbol. Must yield from reconnection logic."""

    def _check_connection(self) -> None:
        """Raise if the provider is not connected."""
        if not self.connection.connected:
            raise ProviderDisconnectedError(
                f"Provider {self.provider_type.value} is not connected."
            )

    def _check_rate_limit(self) -> None:
        """Check and enforce rate limits."""
        if not self.rate_limiter.check():
            raise RateLimitExceededError(
                f"Rate limit exceeded: {self.rate_limiter.max_requests_per_minute}/min"
            )

    def _check_freshness(self, event: MarketDataEvent) -> DataStatus:
        """Check the freshness of a market-data event.

        Per AD-021: reject stale or invalid market data.
        Returns the data status (FRESH/STALE/INVALID).
        """
        if self.freshness.is_stale(event):
            return DataStatus.STALE
        return DataStatus.FRESH

    def _check_duplicate(self, event: MarketDataEvent) -> bool:
        """Check if an event is a duplicate.

        Per Section 08.1: duplicate detection.
        Returns True if the event is a duplicate.
        """
        event_key = str(event.event_id)
        if event_key in self._seen_event_ids:
            return True
        self._seen_event_ids.add(event_key)
        return False

    def _check_sequence(self, symbol: Symbol, sequence: int) -> bool:
        """Check if a sequence number is in order.

        Per Section 08.1: ordering controls.
        Returns True if the sequence is valid (monotonically increasing).
        """
        key = symbol.pair
        last = self._last_sequence.get(key, -1)
        if sequence <= last:
            return False
        self._last_sequence[key] = sequence
        return True

    def _normalize_event(
        self,
        event_type: MarketDataEventType,
        symbol: Symbol,
        payload: Ticker | Trade | Candle | OrderBookSnapshot,
        sequence: int = 0,
    ) -> MarketDataEvent:
        """Normalize a raw event into a MarketDataEvent.

        Per Section 08.1: normalized schemas and timestamp validation.
        Per Section 11.3: event identifier, event type, timestamp, producer identity.
        """
        now = datetime.now(UTC)

        # Determine the timestamp from the payload
        if isinstance(payload, (Ticker, Trade)):
            ts = payload.timestamp
        elif isinstance(payload, Candle):
            ts = payload.close_time
        elif isinstance(payload, OrderBookSnapshot):
            ts = payload.timestamp
        else:
            ts = now

        return MarketDataEvent(
            event_id=EventId.generate(),
            event_type=event_type,
            symbol=symbol,
            provider=self.provider_type,
            timestamp=ts,
            received_at=now,
            sequence=sequence,
            payload=payload,
            provenance=f"{self.provider_type.value}:{self.__class__.__name__}",
        )
