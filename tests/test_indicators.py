"""Tests for deterministic indicators (Phase 03, AD-003, AD-021).

Per AD-003: routine indicators must not depend on LLM availability.
Per AD-021: deterministic signals with exact decimal arithmetic (AD-018).
Per Section 08.1: deterministic indicators.
"""

from datetime import UTC, datetime, timedelta

import pytest

from contracts.indicators import (
    CandleSeries,
    exponential_moving_average,
    relative_strength_index,
    simple_moving_average,
    volatility,
)
from contracts.market_data import Candle, Symbol, Timeframe


def _make_candle(
    symbol: Symbol,
    close: str,
    open_price: str | None = None,
    offset_seconds: int = 0,
) -> Candle:
    """Create a test candle with valid OHLCV."""
    base = float(close)
    o = float(open_price) if open_price else base * 0.995
    h = base * 1.01
    lo = base * 0.99
    now = datetime.now(UTC)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.ONE_MINUTE,
        open=str(o),
        high=str(h),
        low=str(lo),
        close=close,
        volume="100.0",
        open_time=now - timedelta(seconds=offset_seconds),
        close_time=now - timedelta(seconds=offset_seconds) + timedelta(minutes=1),
    )


@pytest.fixture()
def symbol() -> Symbol:
    return Symbol.parse("BTC/USDT")


@pytest.fixture()
def candles(symbol: Symbol) -> list[Candle]:
    """10 candles with prices 100..109."""
    return [_make_candle(symbol, str(100 + i), offset_seconds=(10 - i) * 60) for i in range(10)]


class TestSMA:
    def test_sma_window_5(self, candles: list[Candle]) -> None:
        result = simple_moving_average(candles, window=5)
        assert result.name == "SMA_5"
        assert result.window == 5
        # SMA of last 5 closes: (105+106+107+108+109)/5 = 107
        assert result.value == "107"

    def test_sma_window_1(self, candles: list[Candle]) -> None:
        result = simple_moving_average(candles, window=1)
        assert float(result.value) == 109

    def test_sma_window_too_large(self, candles: list[Candle]) -> None:
        with pytest.raises(ValueError, match="Not enough candles"):
            simple_moving_average(candles, window=20)

    def test_sma_window_zero(self, candles: list[Candle]) -> None:
        with pytest.raises(ValueError, match="Window must be"):
            simple_moving_average(candles, window=0)

    def test_sma_deterministic(self, candles: list[Candle]) -> None:
        r1 = simple_moving_average(candles, window=5)
        r2 = simple_moving_average(candles, window=5)
        assert r1.value == r2.value


class TestEMA:
    def test_ema_window_5(self, candles: list[Candle]) -> None:
        result = exponential_moving_average(candles, window=5)
        assert result.name == "EMA_5"
        assert result.window == 5

    def test_ema_window_too_large(self, candles: list[Candle]) -> None:
        with pytest.raises(ValueError, match="Not enough candles"):
            exponential_moving_average(candles, window=20)

    def test_ema_deterministic(self, candles: list[Candle]) -> None:
        r1 = exponential_moving_average(candles, window=3)
        r2 = exponential_moving_average(candles, window=3)
        assert r1.value == r2.value


class TestRSI:
    def test_rsi_window_14(self, candles: list[Candle]) -> None:
        result = relative_strength_index(candles, window=9)
        assert result.name == "RSI_9"
        assert 0 <= float(result.value) <= 100

    def test_rsi_all_gains(self, symbol: Symbol) -> None:
        """All increasing prices → RSI close to 100."""
        candle_list = [
            _make_candle(symbol, str(100 + i * 10), offset_seconds=(10 - i) * 60) for i in range(12)
        ]
        result = relative_strength_index(candle_list, window=10)
        assert float(result.value) >= 90  # noqa: PLR2004

    def test_rsi_all_losses(self, symbol: Symbol) -> None:
        """All decreasing prices → RSI close to 0."""
        candle_list = [
            _make_candle(symbol, str(1000 - i * 10), offset_seconds=(10 - i) * 60)
            for i in range(12)
        ]
        result = relative_strength_index(candle_list, window=10)
        assert float(result.value) <= 10  # noqa: PLR2004

    def test_rsi_window_too_small(self, candles: list[Candle]) -> None:
        with pytest.raises(ValueError, match="RSI window must be"):
            relative_strength_index(candles, window=1)

    def test_rsi_deterministic(self, candles: list[Candle]) -> None:
        r1 = relative_strength_index(candles, window=9)
        r2 = relative_strength_index(candles, window=9)
        assert r1.value == r2.value


class TestVolatility:
    def test_volatility_window_5(self, candles: list[Candle]) -> None:
        result = volatility(candles, window=5)
        assert result.name == "VOL_5"
        assert float(result.value) >= 0

    def test_volatility_constant_prices(self, symbol: Symbol) -> None:
        """Constant prices → zero volatility."""
        candle_list = [
            _make_candle(symbol, "100.00", offset_seconds=(10 - i) * 60) for i in range(10)
        ]
        result = volatility(candle_list, window=5)
        assert float(result.value) == 0

    def test_volatility_window_too_small(self, candles: list[Candle]) -> None:
        with pytest.raises(ValueError, match="Volatility window must be"):
            volatility(candles, window=1)

    def test_volatility_deterministic(self, candles: list[Candle]) -> None:
        r1 = volatility(candles, window=5)
        r2 = volatility(candles, window=5)
        assert r1.value == r2.value


class TestCandleSeries:
    def test_create_empty(self, symbol: Symbol) -> None:
        series = CandleSeries.create(symbol.pair, "1m")
        assert series.length == 0
        assert series.candles == []

    def test_add_candle(self, symbol: Symbol) -> None:
        series = CandleSeries.create(symbol.pair, "1m")
        candle = _make_candle(symbol, "100")
        assert series.add_candle(candle) is True
        assert series.length == 1

    def test_add_duplicate_candle(self, symbol: Symbol) -> None:
        series = CandleSeries.create(symbol.pair, "1m")
        candle = _make_candle(symbol, "100")
        series.add_candle(candle)
        # Same open_time → duplicate
        assert series.add_candle(candle) is False
        assert series.length == 1

    def test_slice(self, candles: list[Candle]) -> None:
        series = CandleSeries.create("BTC/USDT", "1m")
        for c in candles:
            series.add_candle(c)
        sliced = series.slice(5)
        assert len(sliced) == 5
