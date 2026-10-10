"""Tests for market-data contracts (Phase 03, AD-021).

Per Section 08.1: normalized schemas, timestamp validation,
and data provenance. Per AD-021: reject stale or invalid market data.
"""

from datetime import UTC, datetime, timedelta

import pytest

from contracts.market_data import (
    Candle,
    EventId,
    FreshnessConfig,
    MarketDataEvent,
    MarketDataEventType,
    OrderBookLevel,
    OrderBookSnapshot,
    ProviderType,
    Symbol,
    Ticker,
    Timeframe,
    Trade,
)


class TestSymbol:
    def test_parse_valid_symbol(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        assert sym.base == "BTC"
        assert sym.quote == "USDT"
        assert sym.pair == "BTC/USDT"

    def test_parse_normalizes_case(self) -> None:
        sym = Symbol.parse("btc/usdt")
        assert sym.base == "BTC"
        assert sym.quote == "USDT"

    def test_parse_invalid_no_slash(self) -> None:
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol.parse("BTCUSDT")

    def test_parse_empty_base(self) -> None:
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol.parse("/USDT")

    def test_parse_empty_quote(self) -> None:
        with pytest.raises(ValueError, match="Invalid symbol format"):
            Symbol.parse("BTC/")

    def test_symbol_is_frozen(self) -> None:
        sym = Symbol(base="BTC", quote="USDT")
        with pytest.raises(AttributeError):
            sym.base = "ETH"  # type: ignore[misc]


class TestOrderBookLevel:
    def test_valid_level(self) -> None:
        level = OrderBookLevel(price="50000.00", amount="1.5")
        assert level.price == "50000.00"
        assert level.amount == "1.5"

    def test_zero_price_rejected(self) -> None:
        with pytest.raises(ValueError, match="Price must be positive"):
            OrderBookLevel(price="0", amount="1.5")

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="Amount must be non-negative"):
            OrderBookLevel(price="50000", amount="-1.5")


class TestOrderBookSnapshot:
    def test_valid_snapshot(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        now = datetime.now(UTC)
        book = OrderBookSnapshot(
            symbol=sym,
            bids=(OrderBookLevel(price="49999", amount="1.0"),),
            asks=(OrderBookLevel(price="50001", amount="1.0"),),
            timestamp=now,
            sequence=100,
        )
        assert book.sequence == 100
        assert len(book.bids) == 1
        assert len(book.asks) == 1

    def test_naive_timestamp_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="timezone-aware"):
            OrderBookSnapshot(
                symbol=sym,
                bids=(),
                asks=(),
                timestamp=datetime.now(),
                sequence=0,
            )

    def test_negative_sequence_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="Sequence must be non-negative"):
            OrderBookSnapshot(
                symbol=sym,
                bids=(),
                asks=(),
                timestamp=datetime.now(UTC),
                sequence=-1,
            )


class TestTrade:
    def test_valid_trade(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        trade = Trade(
            trade_id="t1",
            symbol=sym,
            price="50000",
            amount="0.5",
            side="buy",
            timestamp=datetime.now(UTC),
        )
        assert trade.side == "buy"

    def test_invalid_side_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="Invalid trade side"):
            Trade(
                trade_id="t1",
                symbol=sym,
                price="50000",
                amount="0.5",
                side="invalid",
                timestamp=datetime.now(UTC),
            )

    def test_zero_price_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="price must be positive"):
            Trade(
                trade_id="t1",
                symbol=sym,
                price="0",
                amount="0.5",
                side="buy",
                timestamp=datetime.now(UTC),
            )

    def test_zero_amount_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="amount must be positive"):
            Trade(
                trade_id="t1",
                symbol=sym,
                price="50000",
                amount="0",
                side="buy",
                timestamp=datetime.now(UTC),
            )

    def test_naive_timestamp_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="timezone-aware"):
            Trade(
                trade_id="t1",
                symbol=sym,
                price="50000",
                amount="0.5",
                side="buy",
                timestamp=datetime.now(),
            )


class TestCandle:
    def test_valid_candle(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        now = datetime.now(UTC)
        candle = Candle(
            symbol=sym,
            timeframe=Timeframe.ONE_MINUTE,
            open="50000",
            high="50500",
            low="49500",
            close="50200",
            volume="100.5",
            open_time=now,
            close_time=now + timedelta(minutes=1),
        )
        assert candle.open == "50000"

    def test_high_must_be_ge_open(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        now = datetime.now(UTC)
        with pytest.raises(ValueError, match="high must be >= open"):
            Candle(
                symbol=sym,
                timeframe=Timeframe.ONE_MINUTE,
                open="50000",
                high="49000",
                low="49500",
                close="50200",
                volume="100.5",
                open_time=now,
                close_time=now + timedelta(minutes=1),
            )

    def test_low_must_be_le_open(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        now = datetime.now(UTC)
        with pytest.raises(ValueError, match="low must be <= open"):
            Candle(
                symbol=sym,
                timeframe=Timeframe.ONE_MINUTE,
                open="50000",
                high="50500",
                low="51000",
                close="50200",
                volume="100.5",
                open_time=now,
                close_time=now + timedelta(minutes=1),
            )

    def test_negative_volume_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        now = datetime.now(UTC)
        with pytest.raises(ValueError, match="volume must be non-negative"):
            Candle(
                symbol=sym,
                timeframe=Timeframe.ONE_MINUTE,
                open="50000",
                high="50500",
                low="49500",
                close="50200",
                volume="-1",
                open_time=now,
                close_time=now + timedelta(minutes=1),
            )


class TestTicker:
    def test_valid_ticker(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        ticker = Ticker(
            symbol=sym,
            last_price="50000",
            bid="49999",
            ask="50001",
            high_24h="55000",
            low_24h="45000",
            volume_24h="100000",
            timestamp=datetime.now(UTC),
        )
        assert ticker.last_price == "50000"

    def test_ask_must_be_ge_bid(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="ask must be >= bid"):
            Ticker(
                symbol=sym,
                last_price="50000",
                bid="50001",
                ask="49999",
                high_24h="55000",
                low_24h="45000",
                volume_24h="100000",
                timestamp=datetime.now(UTC),
            )

    def test_naive_timestamp_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="timezone-aware"):
            Ticker(
                symbol=sym,
                last_price="50000",
                bid="49999",
                ask="50001",
                high_24h="55000",
                low_24h="45000",
                volume_24h="100000",
                timestamp=datetime.now(),
            )


class TestMarketDataEvent:
    def test_valid_event(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        now = datetime.now(UTC)
        ticker = Ticker(
            symbol=sym,
            last_price="50000",
            bid="49999",
            ask="50001",
            high_24h="55000",
            low_24h="45000",
            volume_24h="100000",
            timestamp=now,
        )
        event = MarketDataEvent(
            event_id=EventId.generate(),
            event_type=MarketDataEventType.TICKER,
            symbol=sym,
            provider=ProviderType.SIMULATED,
            timestamp=now,
            received_at=now,
            payload=ticker,
            provenance="simulated:TestProvider",
        )
        assert event.event_type is MarketDataEventType.TICKER
        assert event.provenance == "simulated:TestProvider"

    def test_naive_timestamp_rejected(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        with pytest.raises(ValueError, match="timezone-aware"):
            MarketDataEvent(
                event_id=EventId.generate(),
                event_type=MarketDataEventType.TICKER,
                symbol=sym,
                provider=ProviderType.SIMULATED,
                timestamp=datetime.now(),
                received_at=datetime.now(UTC),
            )

    def test_age_property(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        old_time = datetime.now(UTC) - timedelta(seconds=60)
        event = MarketDataEvent(
            event_id=EventId.generate(),
            event_type=MarketDataEventType.TICKER,
            symbol=sym,
            provider=ProviderType.SIMULATED,
            timestamp=old_time,
            received_at=old_time,
        )
        assert event.age >= timedelta(seconds=59)


class TestFreshnessConfig:
    def test_fresh_event(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        now = datetime.now(UTC)
        event = MarketDataEvent(
            event_id=EventId.generate(),
            event_type=MarketDataEventType.TICKER,
            symbol=sym,
            provider=ProviderType.SIMULATED,
            timestamp=now,
            received_at=now,
        )
        config = FreshnessConfig(max_age=timedelta(seconds=30))
        assert config.is_fresh(event)
        assert not config.is_stale(event)

    def test_stale_event(self) -> None:
        sym = Symbol.parse("BTC/USDT")
        old_time = datetime.now(UTC) - timedelta(seconds=60)
        event = MarketDataEvent(
            event_id=EventId.generate(),
            event_type=MarketDataEventType.TICKER,
            symbol=sym,
            provider=ProviderType.SIMULATED,
            timestamp=old_time,
            received_at=old_time,
        )
        config = FreshnessConfig(max_age=timedelta(seconds=30))
        assert not config.is_fresh(event)
        assert config.is_stale(event)

    def test_invalid_max_age(self) -> None:
        with pytest.raises(ValueError, match="max_age must be positive"):
            FreshnessConfig(max_age=timedelta(0))

    def test_invalid_warning_threshold(self) -> None:
        with pytest.raises(ValueError, match="warning_threshold must be"):
            FreshnessConfig(max_age=timedelta(seconds=10), warning_threshold=0)


class TestEventId:
    def test_unique_generation(self) -> None:
        id1 = EventId.generate()
        id2 = EventId.generate()
        assert id1 != id2

    def test_string_representation(self) -> None:
        eid = EventId.generate()
        assert str(eid) == str(eid.value)
