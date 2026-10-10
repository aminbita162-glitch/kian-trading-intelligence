"""Tests for backtesting and validation — Phase 06 deliverables 5-8.

Per AD-012: strategy validation pipeline — backtesting, out-of-sample,
walk-forward, paper trading.
Per AD-023: deterministic simulation — same data = same result.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from contracts.market_data import Candle, Symbol, Timeframe
from contracts.strategy import (
    StrategyVersionId,
)
from contracts.validation import (
    ValidationStage,
    ValidationStatus,
    run_backtest,
    run_out_of_sample,
    run_paper_trading,
    run_walk_forward,
)


def _make_candles(count: int, start_price: float = 50000.0) -> list[Candle]:
    """Generate deterministic test candles."""
    symbol = Symbol(base="BTC", quote="USDT")
    tf = Timeframe.ONE_MINUTE
    base_time = datetime.now(UTC)
    candles: list[Candle] = []
    price = start_price
    for i in range(count):
        # Deterministic price movement
        delta = ((i % 5) - 2) * 100
        open_p = price
        close_p = price + delta
        high_p = max(open_p, close_p) + 50
        low_p = min(open_p, close_p) - 50
        if low_p <= 0:
            low_p = 1.0
        if high_p <= 0:
            high_p = 1.0
        if close_p <= 0:
            close_p = 1.0
        candles.append(
            Candle(
                symbol=symbol,
                timeframe=tf,
                open=str(open_p),
                high=str(high_p),
                low=str(low_p),
                close=str(close_p),
                volume=str(1000 + i),
                open_time=base_time + timedelta(minutes=i),
                close_time=base_time + timedelta(minutes=i + 1),
            )
        )
        price = close_p
    return candles


class TestBacktest:
    """Deliverable 5: backtesting — reproducible historical testing."""

    def test_backtest_passes(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(50)
        result = run_backtest(version_id, candles, "buy")
        assert result.status is ValidationStatus.PASSED
        assert result.stage is ValidationStage.BACKTEST
        assert result.candles_used == 50
        assert result.trades > 0

    def test_backtest_deterministic(self) -> None:
        """Same candles + same strategy = same result."""
        version_id = StrategyVersionId.generate()
        candles = _make_candles(30)
        result1 = run_backtest(version_id, candles, "buy")
        result2 = run_backtest(version_id, candles, "buy")
        assert result1.total_return_pct == result2.total_return_pct
        assert result1.win_rate_pct == result2.win_rate_pct

    def test_backtest_empty_candles(self) -> None:
        version_id = StrategyVersionId.generate()
        result = run_backtest(version_id, [], "buy")
        assert result.status is ValidationStatus.FAILED

    def test_backtest_insufficient_candles(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(2)
        result = run_backtest(version_id, candles, "buy")
        assert result.status is ValidationStatus.FAILED


class TestOutOfSample:
    """Deliverable 6: out-of-sample testing."""

    def test_out_of_sample_runs(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(50)
        result = run_out_of_sample(version_id, candles, "buy")
        assert result.stage is ValidationStage.OUT_OF_SAMPLE
        assert result.candles_used > 0

    def test_out_of_sample_deterministic(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(50)
        r1 = run_out_of_sample(version_id, candles, "buy")
        r2 = run_out_of_sample(version_id, candles, "buy")
        assert r1.total_return_pct == r2.total_return_pct

    def test_out_of_sample_empty(self) -> None:
        version_id = StrategyVersionId.generate()
        result = run_out_of_sample(version_id, [], "buy")
        assert result.status is ValidationStatus.FAILED


class TestWalkForward:
    """Deliverable 7: walk-forward validation."""

    def test_walk_forward_runs(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(100)
        result = run_walk_forward(version_id, candles, "buy", window_size=10, step_size=5)
        assert len(result.windows) > 0

    def test_walk_forward_deterministic(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(100)
        r1 = run_walk_forward(version_id, candles, "buy", window_size=10, step_size=5)
        r2 = run_walk_forward(version_id, candles, "buy", window_size=10, step_size=5)
        assert r1.avg_test_return_pct == r2.avg_test_return_pct

    def test_walk_forward_insufficient_data(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(10)
        result = run_walk_forward(version_id, candles, "buy", window_size=20, step_size=10)
        assert not result.passed
        assert len(result.windows) == 0

    def test_walk_forward_windows_are_disjoint(self) -> None:
        """Walk-forward windows should not overlap."""
        version_id = StrategyVersionId.generate()
        candles = _make_candles(100)
        result = run_walk_forward(version_id, candles, "buy", window_size=10, step_size=10)
        for w in result.windows:
            assert w.calibrate_end == w.test_start  # contiguous
            assert w.calibrate_start < w.calibrate_end
            assert w.test_start < w.test_end


class TestPaperTrading:
    """Deliverable 8: paper trading — simulated execution."""

    def test_paper_trading_runs(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(30)
        result = run_paper_trading(version_id, candles, "buy")
        assert result.candles_used == 30

    def test_paper_trading_deterministic(self) -> None:
        version_id = StrategyVersionId.generate()
        candles = _make_candles(30)
        r1 = run_paper_trading(version_id, candles, "buy")
        r2 = run_paper_trading(version_id, candles, "buy")
        assert r1.total_return_pct == r2.total_return_pct

    def test_paper_trading_empty(self) -> None:
        version_id = StrategyVersionId.generate()
        result = run_paper_trading(version_id, [], "buy")
        assert result.status is ValidationStatus.FAILED
