"""Backtesting and validation contracts for Kian Trading Intelligence.

Per deliverable 5: backtesting — reproducible historical testing.
Per deliverable 6: out-of-sample testing — test on data not used in calibration.
Per deliverable 7: walk-forward validation — rolling window optimization and test.
Per deliverable 8: paper trading — simulated execution on live data.

Per AD-012 (Strategy Validation Pipeline): all of the above must pass before
a strategy may be promoted to ACTIVE status.

Per AD-023 (Digital Twin): deterministic simulation and repeatable verification.

Per Section 08.4: no strategy may be represented as guaranteed profitable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from contracts.market_data import Candle
from contracts.strategy import StrategyVersionId


class ValidationStage(StrEnum):
    """Stages of the strategy validation pipeline (Section 08.4)."""

    BACKTEST = "backtest"
    OUT_OF_SAMPLE = "out_of_sample"
    WALK_FORWARD = "walk_forward"
    PAPER_TRADING = "paper_trading"


class ValidationStatus(StrEnum):
    """Status of a validation run."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ValidationRunId:
    """Stable identity for a validation run."""

    value: UUID

    @classmethod
    def generate(cls) -> ValidationRunId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


def _to_decimal(value: str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


@dataclass
class BacktestResult:
    """Result of a backtest run (deliverable 5).

    Per AD-023: deterministic — same strategy version + same data = same result.

    Attributes:
        run_id: Stable unique identifier.
        strategy_version_id: Strategy version under test.
        stage: Validation stage.
        status: Run status.
        candles_used: Number of candles in the test window.
        start_time: UTC start of the test window.
        end_time: UTC end of the test window.
        total_return_pct: Net return as percentage.
        win_rate_pct: Percentage of profitable trades.
        max_drawdown_pct: Maximum peak-to-trough drawdown.
        sharpe_ratio: Risk-adjusted return.
        trades: Number of simulated trades.
        timestamp: UTC run completion timestamp.
    """

    run_id: ValidationRunId
    strategy_version_id: StrategyVersionId
    stage: ValidationStage
    status: ValidationStatus = ValidationStatus.PENDING
    candles_used: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None
    total_return_pct: str = "0.0"
    win_rate_pct: str = "0.0"
    max_drawdown_pct: str = "0.0"
    sharpe_ratio: str = "0.0"
    trades: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.start_time is not None and self.start_time.tzinfo is None:
            raise ValueError("start_time must be timezone-aware (UTC).")
        if self.end_time is not None and self.end_time.tzinfo is None:
            raise ValueError("end_time must be timezone-aware (UTC).")

    @property
    def is_passed(self) -> bool:
        return self.status is ValidationStatus.PASSED


@dataclass
class WalkForwardWindow:
    """A single window in walk-forward validation (deliverable 7).

    Walk-forward validation divides data into alternating calibration
    and out-of-sample windows. The calibration window optimizes parameters;
    the out-of-sample window validates them.

    Attributes:
        window_index: 0-based window index.
        calibrate_start: First candle in calibration.
        calibrate_end: Last candle in calibration (exclusive).
        test_start: First candle in out-of-sample test.
        test_end: Last candle in out-of-sample test (exclusive).
        calibrate_return_pct: Return on the calibration window.
        test_return_pct: Return on the out-of-sample test window.
    """

    window_index: int
    calibrate_start: int
    calibrate_end: int
    test_start: int
    test_end: int
    calibrate_return_pct: str = "0.0"
    test_return_pct: str = "0.0"


@dataclass
class WalkForwardResult:
    """Result of walk-forward validation (deliverable 7).

    Per AD-012: walk-forward testing is required before live approval.

    Attributes:
        run_id: Stable unique identifier.
        strategy_version_id: Strategy version under test.
        windows: List of walk-forward windows.
        avg_test_return_pct: Average return across out-of-sample windows.
        degradation_pct: Difference between calibration and test returns.
        passed: Whether the walk-forward validation passed.
        timestamp: UTC run completion timestamp.
    """

    run_id: ValidationRunId
    strategy_version_id: StrategyVersionId
    windows: list[WalkForwardWindow] = field(default_factory=list)
    avg_test_return_pct: str = "0.0"
    degradation_pct: str = "0.0"
    passed: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class PaperTradeResult:
    """Result of a paper-trading run (deliverable 8).

    Per Section 01.3: PAPER mode = simulated trading using approved
    market data or sandbox environments.

    Attributes:
        run_id: Stable unique identifier.
        strategy_version_id: Strategy version under test.
        status: Run status.
        candles_used: Number of candles in the paper-trading window.
        total_return_pct: Net return as percentage.
        trades: Number of simulated trades.
        timestamp: UTC run completion timestamp.
    """

    run_id: ValidationRunId
    strategy_version_id: StrategyVersionId
    status: ValidationStatus = ValidationStatus.PENDING
    candles_used: int = 0
    total_return_pct: str = "0.0"
    trades: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")

    @property
    def is_passed(self) -> bool:
        return self.status is ValidationStatus.PASSED


# ── Deterministic backtesting engine ──


def _simulate_trades(candles: list[Candle], side: str) -> list[Decimal]:
    """Simulate trades on a candle series deterministically.

    A simple deterministic strategy: buy/sell every N candles and compute
    the return. This is a deterministic simulation — same candles always
    produce the same returns.
    """
    MIN_CANDLES_FOR_TRADES = 2

    if len(candles) < MIN_CANDLES_FOR_TRADES:
        return []

    returns: list[Decimal] = []
    TRADE_INTERVAL = 3

    for i in range(TRADE_INTERVAL, len(candles), TRADE_INTERVAL):
        entry = _to_decimal(candles[i - TRADE_INTERVAL].close)
        exit_ = _to_decimal(candles[i].close)
        if side == "buy":
            ret = (exit_ - entry) / entry * Decimal(100)
        else:
            ret = (entry - exit_) / entry * Decimal(100)
        returns.append(ret)

    return returns


def run_backtest(
    strategy_version_id: StrategyVersionId,
    candles: list[Candle],
    side: str,
) -> BacktestResult:
    """Run a deterministic backtest (deliverable 5).

    Per AD-023: deterministic — same candles + same strategy = same result.
    """
    run_id = ValidationRunId.generate()
    if not candles:
        return BacktestResult(
            run_id=run_id,
            strategy_version_id=strategy_version_id,
            stage=ValidationStage.BACKTEST,
            status=ValidationStatus.FAILED,
            candles_used=0,
        )

    returns = _simulate_trades(candles, side)
    candles_used = len(candles)

    if not returns:
        return BacktestResult(
            run_id=run_id,
            strategy_version_id=strategy_version_id,
            stage=ValidationStage.BACKTEST,
            status=ValidationStatus.FAILED,
            candles_used=candles_used,
            start_time=candles[0].open_time,
            end_time=candles[-1].close_time,
        )

    total_return = sum(returns, Decimal(0))
    wins = sum(1 for r in returns if r > 0)
    win_rate = (Decimal(wins) / Decimal(len(returns))) * Decimal(100)

    # Max drawdown
    peak = Decimal(0)
    cumulative = Decimal(0)
    max_dd = Decimal(0)
    for r in returns:
        cumulative += r
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    return BacktestResult(
        run_id=run_id,
        strategy_version_id=strategy_version_id,
        stage=ValidationStage.BACKTEST,
        status=ValidationStatus.PASSED,
        candles_used=candles_used,
        start_time=candles[0].open_time,
        end_time=candles[-1].close_time,
        total_return_pct=str(total_return),
        win_rate_pct=str(win_rate),
        max_drawdown_pct=str(max_dd),
        trades=len(returns),
    )


def run_out_of_sample(
    strategy_version_id: StrategyVersionId,
    all_candles: list[Candle],
    side: str,
    split_ratio: float = 0.7,
) -> BacktestResult:
    """Run out-of-sample testing (deliverable 6).

    Splits data into calibration and out-of-sample sets. Only the
    out-of-sample portion is evaluated — the calibration set is
    excluded from the results.
    """
    if not all_candles:
        return BacktestResult(
            run_id=ValidationRunId.generate(),
            strategy_version_id=strategy_version_id,
            stage=ValidationStage.OUT_OF_SAMPLE,
            status=ValidationStatus.FAILED,
        )

    split_point = int(len(all_candles) * split_ratio)
    oos_candles = all_candles[split_point:]

    if not oos_candles:
        return BacktestResult(
            run_id=ValidationRunId.generate(),
            strategy_version_id=strategy_version_id,
            stage=ValidationStage.OUT_OF_SAMPLE,
            status=ValidationStatus.FAILED,
            candles_used=0,
        )

    result = run_backtest(strategy_version_id, oos_candles, side)
    return BacktestResult(
        run_id=result.run_id,
        strategy_version_id=strategy_version_id,
        stage=ValidationStage.OUT_OF_SAMPLE,
        status=result.status,
        candles_used=result.candles_used,
        start_time=result.start_time,
        end_time=result.end_time,
        total_return_pct=result.total_return_pct,
        win_rate_pct=result.win_rate_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        trades=result.trades,
    )


def run_walk_forward(
    strategy_version_id: StrategyVersionId,
    candles: list[Candle],
    side: str,
    window_size: int = 20,
    step_size: int = 10,
) -> WalkForwardResult:
    """Run walk-forward validation (deliverable 7).

    Divides data into alternating calibration and out-of-sample windows.
    The calibration window is used to simulate parameter optimization;
    the test window validates on unseen data.
    """
    run_id = ValidationRunId.generate()

    if len(candles) < window_size * 2:
        return WalkForwardResult(
            run_id=run_id,
            strategy_version_id=strategy_version_id,
            windows=[],
            passed=False,
        )

    windows: list[WalkForwardWindow] = []
    test_returns: list[Decimal] = []
    calib_returns: list[Decimal] = []
    window_index = 0

    start = 0
    while start + window_size * 2 <= len(candles):
        calibrate = candles[start : start + window_size]
        test = candles[start + window_size : start + window_size * 2]

        calib_returns_raw = _simulate_trades(calibrate, side)
        test_returns_raw = _simulate_trades(test, side)

        calib_ret = sum(calib_returns_raw, Decimal(0))
        test_ret = sum(test_returns_raw, Decimal(0))

        windows.append(
            WalkForwardWindow(
                window_index=window_index,
                calibrate_start=start,
                calibrate_end=start + window_size,
                test_start=start + window_size,
                test_end=start + window_size * 2,
                calibrate_return_pct=str(calib_ret),
                test_return_pct=str(test_ret),
            )
        )

        test_returns.append(test_ret)
        calib_returns.append(calib_ret)
        window_index += 1
        start += step_size

    if not test_returns:
        return WalkForwardResult(
            run_id=run_id,
            strategy_version_id=strategy_version_id,
            windows=windows,
            passed=False,
        )

    avg_test = sum(test_returns, Decimal(0)) / Decimal(len(test_returns))
    avg_calib = sum(calib_returns, Decimal(0)) / Decimal(len(calib_returns))
    degradation = avg_calib - avg_test

    passed = avg_test > Decimal(0)

    return WalkForwardResult(
        run_id=run_id,
        strategy_version_id=strategy_version_id,
        windows=windows,
        avg_test_return_pct=str(avg_test),
        degradation_pct=str(degradation),
        passed=passed,
    )


def run_paper_trading(
    strategy_version_id: StrategyVersionId,
    candles: list[Candle],
    side: str,
) -> PaperTradeResult:
    """Run paper trading (deliverable 8).

    Per Section 01.3: PAPER mode = simulated trading using approved
    market data or sandbox environments. Uses the most recent candles
    as the live-equivalent simulation window.
    """
    run_id = ValidationRunId.generate()

    if not candles:
        return PaperTradeResult(
            run_id=run_id,
            strategy_version_id=strategy_version_id,
            status=ValidationStatus.FAILED,
        )

    returns = _simulate_trades(candles, side)
    total_return = sum(returns, Decimal(0))
    passed = total_return > Decimal(0)

    return PaperTradeResult(
        run_id=run_id,
        strategy_version_id=strategy_version_id,
        status=ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
        candles_used=len(candles),
        total_return_pct=str(total_return),
        trades=len(returns),
    )
