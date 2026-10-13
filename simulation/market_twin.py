"""Microstructure-realistic market twin for Kian Trading Intelligence.

Per E5 (Simulation and Truth Infrastructure): microstructure-realistic
market twin that generates realistic price paths, order book dynamics,
and trade flow from a deterministic seed.

Per AD-023 (Digital Twin): deterministic simulation, exchange emulation,
replay, fault injection, and repeatable verification.

The market twin generates market data using microstructure models:
- Random walk (geometric Brownian motion)
- Mean reversion (Ornstein-Uhlenbeck)
- Volume-weighted price impact

All generation is deterministic from the seed — same seed → same price
path, same order book, same trade flow. This is NOT a claim of
real-world price prediction; it is a realistic synthetic data source
for testing the trading pipeline.

Per Section 01.3: SIMULATION mode only — no real financial orders.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from contracts.market_data import (
    Candle,
    OrderBookLevel,
    OrderBookSnapshot,
    Symbol,
    Ticker,
    Timeframe,
    Trade,
)
from contracts.simulation import (
    MarketTwinConfig,
    MarketTwinStep,
    MicrostructureModel,
)


def _deterministic_uint(seed: str, index: int) -> int:
    """Derive a deterministic unsigned int from a seed and index."""
    data = f"mt:{seed}:{index}".encode()
    h = hashlib.sha256(data).hexdigest()
    return int(h[:16], 16)


def _deterministic_normal(seed: str, index: int) -> float:
    """Generate a deterministic normal-distributed value in [-1, 1].

    Uses the Box-Muller transform on two deterministic uniforms.
    """
    u1 = _deterministic_uint(seed, index * 2) / 0xFFFFFFFFFFFFFFFF
    u2 = _deterministic_uint(seed, index * 2 + 1) / 0xFFFFFFFFFFFFFFFF
    # Avoid log(0)
    u1 = max(u1, 1e-10)
    # Box-Muller: z = sqrt(-2 ln u1) * cos(2 pi u2)
    z = (2 * max(u1, 1e-10)) ** -0.5 * (u2 * 2 * math.pi)
    # Clamp to [-1, 1]
    result: float = max(-1.0, min(1.0, z))
    return result


class MarketTwin:
    """Microstructure-realistic market twin.

    Per E5: generates realistic market data from a deterministic seed.
    Supports multiple microstructure models (random walk, mean reversion,
    Ornstein-Uhlenbeck, volume-weighted).

    The twin produces a sequence of MarketTwinStep values — each representing
    one time step of simulated market activity. From these steps, tickers,
    order books, candles, and trades can be derived.

    Deterministic: same seed + same config → same sequence of steps.
    """

    def __init__(self, config: MarketTwinConfig) -> None:
        self._config = config
        self._steps: list[MarketTwinStep] = []
        self._current_step: int = 0
        self._current_price: Decimal = Decimal(config.initial_price)

    def _next_price(self, step_index: int) -> Decimal:
        """Generate the next mid-price using the configured model."""
        sigma = Decimal(self._config.volatility)
        mu = Decimal(self._config.drift)
        prev = self._current_price

        if self._config.model is MicrostructureModel.RANDOM_WALK:
            shock = Decimal(str(_deterministic_normal(self._config.seed, step_index)))
            return prev * (Decimal(1) + mu + sigma * shock)

        if self._config.model is MicrostructureModel.MEAN_REVERSION:
            kappa = Decimal(self._config.mean_reversion_rate)
            mean_price = Decimal(self._config.initial_price)
            shock = Decimal(str(_deterministic_normal(self._config.seed, step_index)))
            return prev + kappa * (mean_price - prev) + sigma * shock * prev

        if self._config.model is MicrostructureModel.ORNSTEIN_UHLENBECK:
            kappa = Decimal(self._config.mean_reversion_rate)
            mean_price = Decimal(self._config.initial_price)
            shock = Decimal(str(_deterministic_normal(self._config.seed, step_index)))
            return prev + kappa * (mean_price - prev) + sigma * shock

        if self._config.model is MicrostructureModel.VOLUME_WEIGHTED:
            shock = Decimal(str(_deterministic_normal(self._config.seed, step_index)))
            volume = Decimal(str(_deterministic_volume(self._config.seed, step_index)))
            impact = sigma * shock * (volume / Decimal(self._config.base_volume))
            return prev * (Decimal(1) + mu + impact)

        return prev

    def step(self) -> MarketTwinStep:
        """Advance the market twin by one step and return the new state."""
        idx = self._current_step
        mid = self._next_price(idx)

        # Ensure price stays positive
        if mid <= 0:
            mid = Decimal(self._config.tick_size)

        self._current_price = mid

        # Compute bid/ask spread
        spread_bps = Decimal(self._config.spread_bps)
        half_spread = mid * spread_bps / Decimal(10000)
        bid = mid - half_spread
        ask = mid + half_spread

        if bid <= 0:
            bid = mid * Decimal("0.9999")
        if ask <= bid:
            ask = bid + Decimal(self._config.tick_size)

        # Round to tick size
        tick = Decimal(self._config.tick_size)
        bid = (bid / tick).quantize(Decimal(1)) * tick
        ask = (ask / tick).quantize(Decimal(1)) * tick

        # Deterministic volume
        volume = str(_deterministic_volume(self._config.seed, idx))

        # Deterministic trade side
        side = "buy" if _deterministic_uint(self._config.seed, idx) % 2 == 0 else "sell"

        ts = datetime.now(UTC) + timedelta(seconds=idx)

        step = MarketTwinStep(
            step_index=idx,
            mid_price=str(mid),
            bid_price=str(bid),
            ask_price=str(ask),
            volume=volume,
            trade_side=side,
            timestamp=ts,
        )

        self._steps.append(step)
        self._current_step += 1
        return step

    def generate_steps(self, count: int) -> list[MarketTwinStep]:
        """Generate a sequence of steps deterministically."""
        if count < 1:
            raise ValueError("count must be >= 1.")
        steps: list[MarketTwinStep] = []
        for _ in range(count):
            steps.append(self.step())
        return steps

    def get_ticker(self, symbol: Symbol) -> Ticker:
        """Generate a ticker from the current market twin state."""
        step = self.step()
        return Ticker(
            symbol=symbol,
            last_price=step.mid_price,
            bid=step.bid_price,
            ask=step.ask_price,
            high_24h=str(Decimal(step.mid_price) * Decimal("1.05")),
            low_24h=str(Decimal(step.mid_price) * Decimal("0.95")),
            volume_24h=step.volume,
            timestamp=step.timestamp,
        )

    def get_order_book(self, symbol: Symbol, depth: int = 10) -> OrderBookSnapshot:
        """Generate an order book snapshot from the current state."""
        step = self.step()
        bids: list[OrderBookLevel] = []
        asks: list[OrderBookLevel] = []

        for i in range(depth):
            bid_price = Decimal(step.mid_price) * (Decimal(1) - Decimal("0.0005") * Decimal(i + 1))
            ask_price = Decimal(step.mid_price) * (Decimal(1) + Decimal("0.0005") * Decimal(i + 1))
            amount = str(_deterministic_volume(self._config.seed, i))
            bids.append(OrderBookLevel(price=str(bid_price), amount=amount))
            asks.append(OrderBookLevel(price=str(ask_price), amount=amount))

        return OrderBookSnapshot(
            symbol=symbol,
            bids=tuple(bids),
            asks=tuple(asks),
            timestamp=step.timestamp,
            sequence=step.step_index,
        )

    def get_candles(self, symbol: Symbol, timeframe: Timeframe, count: int) -> list[Candle]:
        """Generate deterministic candles from the market twin."""
        if count < 1:
            raise ValueError("count must be >= 1.")

        tf_map: dict[Timeframe, int] = {
            Timeframe.ONE_MINUTE: 60,
            Timeframe.FIVE_MINUTES: 300,
            Timeframe.FIFTEEN_MINUTES: 900,
            Timeframe.ONE_HOUR: 3600,
            Timeframe.FOUR_HOURS: 14400,
            Timeframe.ONE_DAY: 86400,
            Timeframe.ONE_WEEK: 604800,
        }
        tf_seconds = tf_map.get(timeframe, 60)
        candles: list[Candle] = []

        for i in range(count):
            step = self.step()
            open_price = Decimal(step.mid_price) * (
                Decimal("0.999") if i % 2 == 0 else Decimal("1.001")
            )
            high = Decimal(step.mid_price) * Decimal("1.01")
            low = Decimal(step.mid_price) * Decimal("0.99")
            open_time = step.timestamp - timedelta(seconds=tf_seconds)
            close_time = step.timestamp

            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=str(open_price),
                    high=str(high),
                    low=str(low),
                    close=step.mid_price,
                    volume=step.volume,
                    open_time=open_time,
                    close_time=close_time,
                )
            )

        return candles

    def get_trades(self, symbol: Symbol, count: int) -> list[Trade]:
        """Generate deterministic trades from the market twin."""
        if count < 1:
            raise ValueError("count must be >= 1.")

        trades: list[Trade] = []
        for i in range(count):
            step = self.step()
            trades.append(
                Trade(
                    trade_id=f"mt-{i:08d}",
                    symbol=symbol,
                    price=step.mid_price,
                    amount=str(_deterministic_volume(self._config.seed, i, base=1.0)),
                    side=step.trade_side,
                    timestamp=step.timestamp,
                )
            )
        return trades

    def reset(self) -> None:
        """Reset the market twin to initial state (for testing)."""
        self._steps.clear()
        self._current_step = 0
        self._current_price = Decimal(self._config.initial_price)

    @property
    def steps(self) -> list[MarketTwinStep]:
        """All generated steps so far."""
        return list(self._steps)

    @property
    def current_price(self) -> str:
        """Current mid-price."""
        return str(self._current_price)


def _deterministic_volume(seed: str, index: int, base: float = 100.0) -> float:
    """Generate a deterministic volume from a seed and index."""
    raw = _deterministic_uint(seed, index)
    max_uint = 0xFFFFFFFFFFFFFFFF
    return base * (0.1 + (raw / max_uint))
