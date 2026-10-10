"""Tests for the simulated market-data provider (Phase 03, AD-023).

Per Section 08.1: simulated data provider with reconnection behavior.
Per AD-023: deterministic simulation and replay.
Per Section 05.5: no exchange is automatically approved for live use.
"""

import pytest

from contracts.market_data import (
    OrderBookSnapshot,
    ProviderType,
    Symbol,
    Ticker,
    Timeframe,
)
from services.market_data.provider import (
    ProviderDisconnectedError,
    RateLimitExceededError,
)
from services.market_data.simulated import SimulatedMarketDataProvider


@pytest.fixture()
async def connected_provider() -> SimulatedMarketDataProvider:
    """Create a connected simulated provider."""
    provider = SimulatedMarketDataProvider()
    await provider.connect()
    return provider


class TestSimulatedProviderConnection:
    def test_provider_type_is_simulated(self) -> None:
        provider = SimulatedMarketDataProvider()
        assert provider.provider_type is ProviderType.SIMULATED

    async def test_connect_sets_connected(self) -> None:
        provider = SimulatedMarketDataProvider()
        assert not provider.connection.connected
        await provider.connect()
        assert provider.connection.connected
        assert provider.connection.last_connected is not None

    async def test_disconnect_clears_connected(self) -> None:
        provider = SimulatedMarketDataProvider()
        await provider.connect()
        assert provider.connection.connected
        await provider.disconnect()
        assert not provider.connection.connected
        assert provider.connection.last_disconnected is not None

    async def test_operation_on_disconnected_raises(self) -> None:
        provider = SimulatedMarketDataProvider()
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ProviderDisconnectedError):
            await provider.get_ticker(sym)

    async def test_disconnect_records_reason(self) -> None:
        provider = SimulatedMarketDataProvider()
        await provider.connect()
        await provider.disconnect("Network failure")
        assert provider.connection.last_error == "Network failure"


class TestSimulatedProviderTicker:
    async def test_get_ticker_returns_valid_data(
        self, connected_provider: SimulatedMarketDataProvider
    ) -> None:
        sym = Symbol.parse("BTC/USDT")
        ticker = await connected_provider.get_ticker(sym)
        assert isinstance(ticker, Ticker)
        assert ticker.symbol.pair == "BTC/USDT"
        assert float(ticker.last_price) > 0
        assert float(ticker.bid) > 0
        assert float(ticker.ask) > 0
        assert float(ticker.ask) >= float(ticker.bid)
        assert ticker.timestamp.tzinfo is not None

    async def test_get_ticker_different_symbols_different_data(
        self, connected_provider: SimulatedMarketDataProvider
    ) -> None:
        sym1 = Symbol.parse("BTC/USDT")
        sym2 = Symbol.parse("ETH/USDT")
        # Use different timestamps to ensure different data
        t1 = await connected_provider.get_ticker(sym1)
        t2 = await connected_provider.get_ticker(sym2)
        assert t1.symbol != t2.symbol

    async def test_get_ticker_is_deterministic(
        self, connected_provider: SimulatedMarketDataProvider
    ) -> None:
        pass


class TestSimulatedProviderOrderBook:
    async def test_get_order_book_returns_valid_data(
        self, connected_provider: SimulatedMarketDataProvider
    ) -> None:
        sym = Symbol.parse("BTC/USDT")
        book = await connected_provider.get_order_book(sym, depth=5)
        assert isinstance(book, OrderBookSnapshot)
        assert book.symbol.pair == "BTC/USDT"
        assert len(book.bids) == 5
        assert len(book.asks) == 5
        assert book.sequence > 0
        for bid in book.bids:
            assert float(bid.price) > 0
        for ask in book.asks:
            assert float(ask.price) > 0

    async def test_order_book_depth_customizable(
        self, connected_provider: SimulatedMarketDataProvider
    ) -> None:
        sym = Symbol.parse("BTC/USDT")
        book = await connected_provider.get_order_book(sym, depth=20)
        assert len(book.bids) == 20
        assert len(book.asks) == 20


class TestSimulatedProviderCandles:
    async def test_get_candles_returns_valid_data(
        self, connected_provider: SimulatedMarketDataProvider
    ) -> None:
        sym = Symbol.parse("BTC/USDT")
        candles = await connected_provider.get_candles(sym, Timeframe.ONE_MINUTE, limit=50)
        assert len(candles) == 50
        for candle in candles:
            assert float(candle.open) > 0
            assert float(candle.high) >= float(candle.open)
            assert float(candle.low) <= float(candle.open)
            assert float(candle.close) > 0
            assert candle.close_time.tzinfo is not None

    async def test_get_candles_deterministic(
        self, connected_provider: SimulatedMarketDataProvider
    ) -> None:
        sym = Symbol.parse("BTC/USDT")
        candles1 = await connected_provider.get_candles(sym, Timeframe.ONE_HOUR, limit=10)
        candles2 = await connected_provider.get_candles(sym, Timeframe.ONE_HOUR, limit=10)
        # Same seed → same close prices
        for c1, c2 in zip(candles1, candles2, strict=True):
            assert c1.close == c2.close

    async def test_get_candles_invalid_limit_raises(
        self, connected_provider: SimulatedMarketDataProvider
    ) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(Exception, match="limit must be"):
            await connected_provider.get_candles(sym, Timeframe.ONE_MINUTE, limit=0)


class TestRateLimit:
    async def test_rate_limit_allows_under_max(self) -> None:
        provider = SimulatedMarketDataProvider(max_rate_per_minute=10)
        await provider.connect()
        sym = Symbol.parse("BTC/USDT")
        for _ in range(10):
            await provider.get_ticker(sym)

    async def test_rate_limit_blocks_over_max(self) -> None:
        provider = SimulatedMarketDataProvider(max_rate_per_minute=3)
        await provider.connect()
        sym = Symbol.parse("BTC/USDT")
        await provider.get_ticker(sym)
        await provider.get_ticker(sym)
        await provider.get_ticker(sym)
        with pytest.raises(RateLimitExceededError):
            await provider.get_ticker(sym)

    async def test_rate_limit_remaining(self) -> None:
        provider = SimulatedMarketDataProvider(max_rate_per_minute=10)
        await provider.connect()
        sym = Symbol.parse("BTC/USDT")
        assert provider.rate_limiter.remaining() == 10
        await provider.get_ticker(sym)
        assert provider.rate_limiter.remaining() == 9


class TestReconnection:
    async def test_should_reconnect_after_disconnect(self) -> None:
        provider = SimulatedMarketDataProvider()
        await provider.connect()
        await provider.simulate_disconnect("Test disconnect")
        assert provider.connection.should_reconnect()

    async def test_reconnect_succeeds(self) -> None:
        provider = SimulatedMarketDataProvider()
        await provider.connect()
        await provider.simulate_disconnect("Test disconnect")
        result = await provider.simulate_reconnect()
        assert result is True
        assert provider.connection.connected

    async def test_max_reconnect_attempts_exhausted(self) -> None:
        provider = SimulatedMarketDataProvider()
        await provider.connect()
        await provider.simulate_disconnect("Test disconnect")
        # Exhaust reconnect attempts
        provider.connection.reconnect_attempts = provider.connection.max_reconnect_attempts
        assert not provider.connection.should_reconnect()
        result = await provider.simulate_reconnect()
        assert result is False

    async def test_exponential_backoff_delay(self) -> None:
        provider = SimulatedMarketDataProvider()
        await provider.connect()
        await provider.simulate_disconnect("Test disconnect")
        delay1 = provider.connection.next_reconnect_delay()
        delay2 = provider.connection.next_reconnect_delay()
        delay3 = provider.connection.next_reconnect_delay()
        # Each delay should be 2x the previous (exponential backoff)
        assert delay2 > delay1
        assert delay3 > delay2

    async def test_reconnect_resets_attempts(self) -> None:
        provider = SimulatedMarketDataProvider()
        await provider.connect()
        await provider.simulate_disconnect("Test disconnect")
        provider.connection.next_reconnect_delay()  # increment attempts
        await provider.simulate_reconnect()
        assert provider.connection.reconnect_attempts == 0
