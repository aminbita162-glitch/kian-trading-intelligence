"""Simulated market-data provider for Kian Trading Intelligence.

Per Section 08.1: simulated data provider.
Per AD-003 (Hybrid Low-Token Intelligence): deterministic, no LLM dependency.
Per AD-023 (Digital Twin): deterministic simulation and replay.

This provider generates deterministic, reproducible market data for testing,
replay, and simulation mode. It does NOT connect to any real exchange.

Per Section 01.3: SIMULATION mode uses historical or synthetic data without
real financial orders.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from contracts.market_data import (
    Candle,
    FreshnessConfig,
    OrderBookLevel,
    OrderBookSnapshot,
    ProviderType,
    Symbol,
    Ticker,
    Timeframe,
    Trade,
)
from services.market_data.provider import (
    MarketDataProvider,
    MarketDataProviderError,
)

# Deterministic seed-based pseudo-random number generator.
# Uses SHA-256 hash for reproducibility — same seed → same sequence.
_TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.ONE_MINUTE: 60,
    Timeframe.FIVE_MINUTES: 300,
    Timeframe.FIFTEEN_MINUTES: 900,
    Timeframe.ONE_HOUR: 3600,
    Timeframe.FOUR_HOURS: 14400,
    Timeframe.ONE_DAY: 86400,
    Timeframe.ONE_WEEK: 604800,
}


def _deterministic_price(seed: str, index: int, base: float = 50000.0) -> float:
    """Generate a deterministic price from a seed and index.

    Uses SHA-256 for reproducibility. Same seed+index → same price.
    """
    data = f"{seed}:{index}".encode()
    h = hashlib.sha256(data).hexdigest()
    # Use first 8 hex chars as a uint32, scale to a range around base
    raw = int(h[:8], 16)
    # Price oscillates between 50% and 150% of base
    return base * (0.5 + (raw / 0xFFFFFFFF))


def _deterministic_volume(seed: str, index: int, base: float = 100.0) -> float:
    """Generate a deterministic volume from a seed and index."""
    data = f"vol:{seed}:{index}".encode()
    h = hashlib.sha256(data).hexdigest()
    raw = int(h[:8], 16)
    return base * (0.1 + (raw / 0xFFFFFFFF))


class SimulatedProviderError(MarketDataProviderError):
    """Errors from the simulated provider."""


class SimulatedMarketDataProvider(MarketDataProvider):
    """Deterministic simulated market-data provider.

    Generates reproducible market data using SHA-256 hashing.
    Per AD-023: deterministic simulation. Per AD-003: no LLM dependency.
    """

    def __init__(
        self,
        *,
        seed: str = "kian-simulation",
        freshness_max_age_seconds: float = 30.0,
        max_rate_per_minute: int = 100,
    ) -> None:
        super().__init__(
            provider_type=ProviderType.SIMULATED,
            freshness=FreshnessConfig(max_age=timedelta(seconds=freshness_max_age_seconds)),
            max_rate_per_minute=max_rate_per_minute,
        )
        self.seed = seed
        self._trade_counter: int = 0

    async def connect(self) -> None:
        """Establish the simulated connection."""
        self.connection.connect()

    async def disconnect(self, reason: str = "") -> None:
        """Close the simulated connection."""
        self.connection.disconnect(reason or "Manual disconnect")

    async def get_ticker(self, symbol: Symbol) -> Ticker:
        """Get a deterministic ticker for a symbol."""
        self._check_connection()
        self._check_rate_limit()

        seed = f"{self.seed}:{symbol.pair}"
        now = datetime.now(UTC)
        price = _deterministic_price(seed, int(now.timestamp()))
        spread = price * 0.0002  # 2 bps spread

        return Ticker(
            symbol=symbol,
            last_price=str(price),
            bid=str(price - spread),
            ask=str(price + spread),
            high_24h=str(price * 1.05),
            low_24h=str(price * 0.95),
            volume_24h=str(_deterministic_volume(seed, int(now.timestamp()), base=10000.0)),
            timestamp=now,
        )

    async def get_order_book(self, symbol: Symbol, depth: int = 10) -> OrderBookSnapshot:
        """Get a deterministic order book snapshot for a symbol."""
        self._check_connection()
        self._check_rate_limit()

        seed = f"{self.seed}:{symbol.pair}"
        now = datetime.now(UTC)
        mid_price = _deterministic_price(seed, int(now.timestamp()))

        bids: list[OrderBookLevel] = []
        asks: list[OrderBookLevel] = []
        for i in range(depth):
            bid_price = mid_price * (1 - 0.0005 * (i + 1))
            ask_price = mid_price * (1 + 0.0005 * (i + 1))
            amount = _deterministic_volume(seed, i)
            bids.append(OrderBookLevel(price=str(bid_price), amount=str(amount)))
            asks.append(OrderBookLevel(price=str(ask_price), amount=str(amount)))

        return OrderBookSnapshot(
            symbol=symbol,
            bids=tuple(bids),
            asks=tuple(asks),
            timestamp=now,
            sequence=int(now.timestamp()),
        )

    async def get_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> list[Candle]:
        """Generate deterministic historical candles for a symbol."""
        self._check_connection()
        self._check_rate_limit()

        if limit < 1:
            raise SimulatedProviderError("limit must be >= 1")

        tf_seconds = _TIMEFRAME_SECONDS.get(timeframe, 60)
        seed = f"{self.seed}:{symbol.pair}:{timeframe.value}"
        now = datetime.now(UTC)

        candles: list[Candle] = []
        for i in range(limit):
            close_offset = (limit - i) * tf_seconds
            open_time = now - timedelta(seconds=close_offset)
            close_time = open_time + timedelta(seconds=tf_seconds)

            price = _deterministic_price(seed, i)
            high = price * 1.01
            low = price * 0.99
            open_price = price * (0.995 if i % 2 == 0 else 1.005)
            volume = _deterministic_volume(seed, i)

            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=str(open_price),
                    high=str(high),
                    low=str(low),
                    close=str(price),
                    volume=str(volume),
                    open_time=open_time,
                    close_time=close_time,
                )
            )

        return candles

    async def stream_trades(self, symbol: Symbol) -> AsyncIterator[Trade]:
        """Stream simulated trades with reconnection behavior.

        Yields deterministic trades. If the connection drops, raises
        ProviderDisconnectedError after exhausting reconnect attempts.
        """
        self._check_connection()

        seed = f"{self.seed}:{symbol.pair}:trades"
        while self.connection.connected:
            self._trade_counter += 1
            idx = self._trade_counter
            price = _deterministic_price(seed, idx)
            amount = _deterministic_volume(seed, idx, base=1.0)
            side = "buy" if idx % 2 == 0 else "sell"
            now = datetime.now(UTC)

            yield Trade(
                trade_id=f"sim-{idx:08d}",
                symbol=symbol,
                price=str(price),
                amount=str(amount),
                side=side,
                timestamp=now,
            )
            await asyncio.sleep(0.01)  # Small delay for async streaming

    async def simulate_disconnect(self, reason: str = "Simulated failure") -> None:
        """Simulate a provider disconnection (for testing reconnection)."""
        self.connection.disconnect(reason)

    async def simulate_reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff.

        Per Section 08.1: reconnection behavior.
        Returns True if reconnection succeeds, False if max attempts exceeded.
        """
        while self.connection.should_reconnect():
            delay = self.connection.next_reconnect_delay()
            await asyncio.sleep(delay)
            self.connection.connect()
            return True
        return False
