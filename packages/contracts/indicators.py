"""Deterministic technical indicators for market data.

Per AD-003 (Hybrid Low-Token Intelligence): routine indicators must not
depend on LLM availability. All indicators are deterministic.

Per AD-021 (Shared Market Data): eligible indicators may be shared across
tenants where the underlying market data is shareable.

Per Section 08.1: normalized, deterministic market-data processing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from contracts.market_data import Candle


def _to_decimal(value: str | Decimal) -> Decimal:
    """Convert a string or Decimal to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


@dataclass(frozen=True)
class IndicatorResult:
    """Result of a deterministic indicator calculation.

    Attributes:
        name: Indicator name.
        value: Computed value as string for exact decimal (AD-018).
        timestamp: ISO timestamp of the computation point.
        window: Number of data points used.
    """

    name: str
    value: str
    timestamp: str
    window: int


def simple_moving_average(
    candles: Sequence[Candle],
    window: int,
    price_field: str = "close",
) -> IndicatorResult:
    """Compute the simple moving average (SMA) over the last N candles.

    Deterministic: same candles + window → same result.
    """
    if window < 1:
        raise ValueError("Window must be >= 1.")
    if window > len(candles):
        raise ValueError(f"Not enough candles for window {window}: have {len(candles)}.")

    prices = [_to_decimal(getattr(c, price_field)) for c in candles[-window:]]
    sma = sum(prices, Decimal(0)) / Decimal(window)

    last = candles[-1]
    return IndicatorResult(
        name=f"SMA_{window}",
        value=str(sma),
        timestamp=last.close_time.isoformat(),
        window=window,
    )


def exponential_moving_average(
    candles: Sequence[Candle],
    window: int,
    price_field: str = "close",
) -> IndicatorResult:
    """Compute the exponential moving average (EMA) over the last N candles.

    Deterministic: same candles + window → same result.
    """
    if window < 1:
        raise ValueError("Window must be >= 1.")
    if window > len(candles):
        raise ValueError(f"Not enough candles for window {window}: have {len(candles)}.")

    alpha = Decimal(2) / Decimal(window + 1)
    prices = [_to_decimal(getattr(c, price_field)) for c in candles]

    ema = prices[0]
    for price in prices[1:]:
        ema = price * alpha + ema * (Decimal(1) - alpha)

    last = candles[-1]
    return IndicatorResult(
        name=f"EMA_{window}",
        value=str(ema),
        timestamp=last.close_time.isoformat(),
        window=window,
    )


def relative_strength_index(
    candles: Sequence[Candle],
    window: int = 14,
) -> IndicatorResult:
    """Compute the Relative Strength Index (RSI) over the last N candles.

    Deterministic: same candles + window → same result.
    RSI = 100 - 100 / (1 + RS) where RS = avg_gain / avg_loss.
    """
    RSI_MIN_WINDOW = 2

    if window < RSI_MIN_WINDOW:
        raise ValueError(f"RSI window must be >= {RSI_MIN_WINDOW}.")
    if window + 1 > len(candles):
        raise ValueError(f"Not enough candles for RSI window {window}: have {len(candles)}.")

    closes = [_to_decimal(c.close) for c in candles]
    gains: list[Decimal] = []
    losses: list[Decimal] = []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(Decimal(0))
        else:
            gains.append(Decimal(0))
            losses.append(abs(diff))

    avg_gain = sum(gains[-window:], Decimal(0)) / Decimal(window)
    avg_loss = sum(losses[-window:], Decimal(0)) / Decimal(window)

    if avg_loss == 0:
        rsi = Decimal(100)
    else:
        rs = avg_gain / avg_loss
        rsi = Decimal(100) - Decimal(100) / (Decimal(1) + rs)

    last = candles[-1]
    return IndicatorResult(
        name=f"RSI_{window}",
        value=str(rsi),
        timestamp=last.close_time.isoformat(),
        window=window,
    )


def volatility(
    candles: Sequence[Candle],
    window: int,
) -> IndicatorResult:
    """Compute the rolling volatility (standard deviation of close prices).

    Deterministic: same candles + window → same result.
    """
    VOL_MIN_WINDOW = 2

    if window < VOL_MIN_WINDOW:
        raise ValueError(f"Volatility window must be >= {VOL_MIN_WINDOW}.")
    if window > len(candles):
        raise ValueError(f"Not enough candles for window {window}: have {len(candles)}.")

    prices = [_to_decimal(c.close) for c in candles[-window:]]
    mean = sum(prices, Decimal(0)) / Decimal(window)
    sq_diffs = [(p - mean) ** 2 for p in prices]
    variance = sum(sq_diffs, Decimal(0)) / Decimal(window)

    last = candles[-1]
    return IndicatorResult(
        name=f"VOL_{window}",
        value=str(variance.sqrt()),
        timestamp=last.close_time.isoformat(),
        window=window,
    )


@dataclass
class CandleSeries:
    """A series of candles for indicator computation and historical storage.

    Per Section 08.1: historical storage and deterministic replay.
    """

    symbol: str
    timeframe: str
    candles: list[Candle]
    _dedup_keys: set[str]

    def __post_init__(self) -> None:
        if not self.candles and not self._dedup_keys:
            self._dedup_keys = set()

    @classmethod
    def create(cls, symbol: str, timeframe: str) -> CandleSeries:
        """Create an empty candle series."""
        return cls(symbol=symbol, timeframe=timeframe, candles=[], _dedup_keys=set())

    def add_candle(self, candle: Candle) -> bool:
        """Add a candle to the series with duplicate detection.

        Returns True if added, False if duplicate detected.
        Per Section 08.1: duplicate detection.
        """
        key = f"{candle.symbol.pair}_{candle.open_time.isoformat()}"
        if key in self._dedup_keys:
            return False
        self._dedup_keys.add(key)
        self.candles.append(candle)
        return True

    @property
    def length(self) -> int:
        return len(self.candles)

    def slice(self, count: int) -> list[Candle]:
        """Return the last N candles for indicator computation."""
        if count > len(self.candles):
            return self.candles[:]
        return self.candles[-count:]
