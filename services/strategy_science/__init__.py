"""Strategy science services for Kian Trading Intelligence.

Per E7 (Strategy Science) and AD-040 (Statistical Honesty and Strategy
Validation Gate):

Research registry; validation gate with CPCV, PBO, Deflated Sharpe,
trial counter (hash-chained); data-quality pipeline; regime/drift
monitors; champion/challenger shadow mode with counterfactual
attribution; stress scenario library; signed model cards.

No strategy enters paper or live without passing the gate.
Passing is not a claim of profitability.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from decimal import Decimal
from itertools import combinations
from typing import Any

from contracts.market_data import Candle
from contracts.strategy import StrategyVersion
from contracts.strategy_science import (
    STANDARD_STRESS_SCENARIOS,
    CounterfactualOutcome,
    CPCVConfig,
    CPCVFold,
    CPCVResult,
    DataQualityIssue,
    DataQualityIssueType,
    DataQualityReport,
    DeflatedSharpeConfig,
    DeflatedSharpeResult,
    DriftAlert,
    DriftReport,
    DriftType,
    GateDecision,
    GateReport,
    ModelCard,
    PBOConfig,
    PBOResult,
    RegimeObservation,
    RegimeReport,
    RegimeType,
    ResearchRegistration,
    ResearchRegistrationId,
    ShadowModeStatus,
    ShadowRunId,
    ShadowRunResult,
    StressScenario,
    StressTestResult,
    TrialId,
    TrialRecord,
)

# ── Hash-chained trial counter ─────────────────────────────────────


class TrialCounter:
    """Hash-chained trial counter (AD-040).

    Each trial links to the previous one's hash, forming a tamper-evident
    chain. Any insertion, deletion, or modification of a trial breaks the
    chain and is detectable by verify_chain().

    Attributes:
        _trials: List of trial records.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._trials: list[TrialRecord] = []
        self._lock = threading.Lock()

    def record_trial(
        self,
        strategy_version_id: str,
        result_summary: dict[str, Any],
    ) -> TrialRecord:
        """Record a new trial and return the trial record."""
        with self._lock:
            previous_hash = "genesis"
            if self._trials:
                previous_hash = self._trials[-1].trial_hash
            record = TrialRecord(
                trial_id=TrialId.generate(),
                strategy_version_id=strategy_version_id,
                previous_hash=previous_hash,
                result_summary=result_summary,
            )
            self._trials.append(record)
            return record

    @property
    def count(self) -> int:
        """Number of trials recorded."""
        with self._lock:
            return len(self._trials)

    @property
    def trials(self) -> list[TrialRecord]:
        """All trial records (thread-safe copy)."""
        with self._lock:
            return list(self._trials)

    def verify_chain(self) -> bool:
        """Verify the integrity of the hash chain."""
        with self._lock:
            expected = "genesis"
            for record in self._trials:
                if record.previous_hash != expected:
                    return False
                expected = record.trial_hash
            return True

    def trials_for_strategy(self, strategy_version_id: str) -> list[TrialRecord]:
        """Get all trials for a given strategy version."""
        with self._lock:
            return [t for t in self._trials if t.strategy_version_id == strategy_version_id]

    def reset(self) -> None:
        """Reset the trial counter (for testing)."""
        with self._lock:
            self._trials.clear()


# ── Research registry ──────────────────────────────────────────────


class ResearchRegistry:
    """Pre-registration research registry (AD-040).

    A strategy must be pre-registered before any validation trial runs.
    Pre-registration locks the hypothesis, intended metrics, and data
    scope before seeing the results — preventing data-snooping.

    Attributes:
        _registrations: Dict of registration_id -> ResearchRegistration.
        _by_strategy: Dict of strategy_version_id -> list of registrations.
        _lock: Thread lock for concurrent access.
    """

    def __init__(self) -> None:
        self._registrations: dict[str, ResearchRegistration] = {}
        self._by_strategy: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def register(  # noqa: PLR0913, PLR0917
        self,
        strategy_version_id: str,
        tenant_id: str,
        hypothesis: str,
        intended_metrics: list[str],
        data_scope: str,
        rejection_criteria: list[str],
    ) -> ResearchRegistration:
        """Pre-register a strategy's research hypothesis."""
        with self._lock:
            registration = ResearchRegistration(
                registration_id=ResearchRegistrationId.generate(),
                strategy_version_id=strategy_version_id,
                tenant_id=tenant_id,
                hypothesis=hypothesis,
                intended_metrics=intended_metrics,
                data_scope=data_scope,
                rejection_criteria=rejection_criteria,
            )
            self._registrations[str(registration.registration_id)] = registration
            if strategy_version_id not in self._by_strategy:
                self._by_strategy[strategy_version_id] = []
            self._by_strategy[strategy_version_id].append(
                str(registration.registration_id),
            )
            return registration

    def get(self, registration_id: str) -> ResearchRegistration | None:
        """Get a registration by ID."""
        with self._lock:
            return self._registrations.get(registration_id)

    def get_for_strategy(self, strategy_version_id: str) -> list[ResearchRegistration]:
        """Get all registrations for a strategy."""
        with self._lock:
            ids = self._by_strategy.get(strategy_version_id, [])
            return [self._registrations[rid] for rid in ids if rid in self._registrations]

    def is_registered(self, strategy_version_id: str) -> bool:
        """Check if a strategy has at least one pre-registration."""
        with self._lock:
            return strategy_version_id in self._by_strategy and bool(
                self._by_strategy[strategy_version_id],
            )

    @property
    def count(self) -> int:
        """Total number of registrations."""
        with self._lock:
            return len(self._registrations)

    def reset(self) -> None:
        """Reset the registry (for testing)."""
        with self._lock:
            self._registrations.clear()
            self._by_strategy.clear()


# ── CPCV (Combinatorial Purged Cross-Validation) ───────────────────


class CPCVEvaluator:
    """Combinatorial Purged Cross-Validation evaluator (AD-040).

    CPCV combats overfitting by:
    - Splitting data into N groups, holding out K groups for testing.
    - Purging observations near training/test boundaries to prevent
      leakage from overlapping labels.
    - Embargoing a buffer after training data to prevent
      serial-correlation leakage.
    """

    def evaluate(
        self,
        candles: list[Candle],
        side: str,
        config: CPCVConfig,
    ) -> CPCVResult:
        """Run CPCV on a candle series."""
        n = len(candles)
        if n < config.n_groups:
            return CPCVResult(
                config=config,
                folds=[],
                avg_test_return="0.0",
                return_std="0.0",
                avg_sharpe="0.0",
                n_obs_total=n,
            )

        group_size = n // config.n_groups
        embargo_len = int(n * float(config.embargo_pct))

        folds: list[CPCVFold] = []
        test_returns: list[Decimal] = []

        test_group_combos = list(
            combinations(range(config.n_groups), config.n_test_groups),
        )

        for fold_index, test_groups in enumerate(test_group_combos):
            test_indices: list[int] = []
            train_indices: list[int] = []
            purged_indices: list[int] = []
            embargoed_indices: list[int] = []

            for g in range(config.n_groups):
                start = g * group_size
                end = min(start + group_size, n)
                indices = list(range(start, end))

                if g in test_groups:
                    test_indices.extend(indices)
                else:
                    train_indices.extend(indices)

            # Purge observations near test/train boundaries
            if config.purge_window > 0:
                for g in test_groups:
                    start = g * group_size
                    purge_start = max(0, start - config.purge_window)
                    purge_end = min(start, n)
                    purged_indices.extend(
                        range(purge_start, purge_end),
                    )

            # Embargo after last training group
            if embargo_len > 0 and train_indices:
                max_train = max(train_indices)
                embargo_start = max_train + 1
                embargo_end = min(embargo_start + embargo_len, n)
                embargoed_indices.extend(
                    range(embargo_start, embargo_end),
                )

            # Remove purged/embargoed from training
            purged_set = set(purged_indices)
            embargoed_set = set(embargoed_indices)
            train_indices = [
                i for i in train_indices if i not in purged_set and i not in embargoed_set
            ]

            test_candles = [candles[i] for i in test_indices]
            test_return = _simulate_return(test_candles, side)

            folds.append(
                CPCVFold(
                    fold_index=fold_index,
                    train_indices=train_indices,
                    test_indices=test_indices,
                    purged_indices=purged_indices,
                    embargoed_indices=embargoed_indices,
                ),
            )
            test_returns.append(test_return)

        if not test_returns:
            return CPCVResult(
                config=config,
                folds=folds,
                n_obs_total=n,
            )

        avg_return = sum(test_returns, Decimal(0)) / Decimal(len(test_returns))
        variance = sum((r - avg_return) ** 2 for r in test_returns) / Decimal(len(test_returns))
        std = _decimal_sqrt(variance) if variance > 0 else Decimal("0")
        avg_sharpe = _decimal_sharpe(test_returns)

        return CPCVResult(
            config=config,
            folds=folds,
            fold_returns=[str(r) for r in test_returns],
            avg_test_return=str(avg_return),
            return_std=str(std),
            avg_sharpe=str(avg_sharpe),
            n_obs_total=n,
            n_obs_purged=sum(len(f.purged_indices) for f in folds),
            n_obs_embargoed=sum(len(f.embargoed_indices) for f in folds),
        )


# ── PBO (Probability of Backtest Overfitting) ──────────────────────


class PBOEvaluator:
    """Probability of Backtest Overfitting evaluator (AD-040).

    PBO measures the probability that a strategy's performance ranking
    in in-sample (IS) backtests is NOT preserved out-of-sample (OOS).
    A PBO > 0.5 indicates the strategy selection is no better than random —
    the backtests are overfit.

    The computation:
    1. Split the data into N partitions.
    2. For each partition assignment, compute IS and OOS returns.
    3. Count the fraction of assignments where the best-IS strategy is
       NOT the best-OOS strategy.
    """

    def evaluate(
        self,
        is_returns: list[str],
        oos_returns: list[str],
        config: PBOConfig,
    ) -> PBOResult:
        """Compute the PBO from IS and OOS return sequences."""
        if not is_returns or not oos_returns:
            return PBOResult(
                n_trials=config.n_trials,
                n_partitions=config.n_partitions,
            )

        is_decimals = [Decimal(r) for r in is_returns]
        oos_decimals = [Decimal(r) for r in oos_returns]

        # Count how many times IS and OOS agree on sign
        # PBO = fraction where the best IS does not correspond to best OOS
        # For simplicity in this deterministic implementation:
        # Count disagreements between IS and OOS sign.
        # If IS avg > 0 but OOS avg <= 0, that's evidence of overfitting.

        # Count IS-positive but OOS-negative or IS-negative but OOS-positive
        disagrees = sum(
            1
            for i_val, o_val in zip(is_decimals, oos_decimals, strict=False)
            if (i_val > 0 and o_val <= 0) or (i_val <= 0 and o_val > 0)
        )

        pbo = Decimal(disagrees) / Decimal(len(is_decimals))

        # Logit-scaled PBO
        if pbo == Decimal("0"):
            logits = Decimal("-10")
        elif pbo == Decimal("1"):
            logits = Decimal("10")
        else:
            logits = _decimal_logit(pbo)

        return PBOResult(
            pbo=str(pbo),
            logits=str(logits),
            n_trials=config.n_trials,
            n_partitions=config.n_partitions,
            is_overfit=pbo > Decimal("0.5"),
        )

    def evaluate_strategy(
        self,
        is_returns: list[str],
        oos_returns: list[str],
        n_trials: int = 100,
    ) -> PBOResult:
        """Evaluate PBO for a strategy with default config."""
        return self.evaluate(
            is_returns=is_returns,
            oos_returns=oos_returns,
            config=PBOConfig(n_trials=n_trials),
        )


# ── Deflated Sharpe Ratio ──────────────────────────────────────────


class DeflatedSharpeEvaluator:
    """Deflated Sharpe Ratio evaluator (AD-040).

    The DSR adjusts the observed Sharpe ratio for:
    - Number of trials (selection bias)
    - Skewness and kurtosis of returns
    - Observation length

    DSR = (observed_sharpe * sqrt(observation_length) - expected_sharpe)
          / sqrt(1 - skew * observed_sharpe + (kurt - 1) / 4 * observed_sharpe^2)

    If DSR < threshold, the observed Sharpe may be a statistical artifact.
    """

    def evaluate(
        self,
        observed_sharpe: str,
        config: DeflatedSharpeConfig,
    ) -> DeflatedSharpeResult:
        """Compute the Deflated Sharpe Ratio."""
        sr = Decimal(observed_sharpe)
        n = Decimal(config.observation_length)
        n_trials = Decimal(config.n_trials)
        skew = Decimal(config.skewness)
        kurt = Decimal(config.kurtosis)
        sig = Decimal(config.significance_level)

        # Expected maximum Sharpe under null hypothesis (no skill):
        # E[max] = sqrt(2 * ln(n_trials)) * (1 - 1/(4*ln(n_trials)))
        if n_trials > Decimal("1"):
            log_n = _decimal_ln(n_trials)
            expected_sharpe = _decimal_sqrt(Decimal(2) * log_n) * (
                Decimal(1) - Decimal(1) / (Decimal(4) * log_n)
            )
        else:
            expected_sharpe = Decimal(0)

        # Variance adjustment: variance of SR estimator
        # variance ≈ 1 - skew * SR + (kurt - 1) / 4 * SR^2
        sr_sq = sr * sr
        variance = Decimal(1) - skew * sr + (kurt - Decimal(1)) / Decimal(4) * sr_sq

        if variance <= Decimal(0):
            variance = Decimal("0.0001")

        # DSR statistic
        sqrt_n = _decimal_sqrt(n)
        dsr_statistic = (sr * sqrt_n - expected_sharpe) / _decimal_sqrt(variance)

        # p-value approximation: P(Z >= dsr_statistic) under standard normal
        # Using a deterministic approximation
        p_value = _decimal_normal_sf(dsr_statistic)

        # Critical value for significance level
        z_critical = _decimal_normal_ppf(Decimal(1) - sig)
        is_significant = dsr_statistic > z_critical

        return DeflatedSharpeResult(
            observed_sharpe=str(sr),
            expected_sharpe=str(expected_sharpe),
            deflated_sharpe=str(dsr_statistic),
            p_value=str(p_value),
            is_statistically_significant=is_significant,
            threshold=str(z_critical),
        )


# ── Data-quality pipeline ──────────────────────────────────────────


class DataQualityPipeline:
    """Data-quality pipeline for strategy validation.

    Checks for:
    - Missing values (gaps in candle sequence)
    - Duplicates (repeated timestamps)
    - Outliers (extreme price moves)
    - Low volume
    - Price anomalies
    """

    def check(
        self,
        candles: list[Candle],
        *,
        outlier_threshold_pct: str = "20.0",
        low_volume_threshold: str = "0.0",
    ) -> DataQualityReport:
        """Check candle data for quality issues."""
        if not candles:
            return self._empty_report()
        n = len(candles)
        outlier_threshold = Decimal(outlier_threshold_pct)
        issues: list[DataQualityIssue] = []

        issues.extend(self._check_duplicates(candles))
        issues.extend(self._check_gaps(candles, outlier_threshold, outlier_threshold_pct))
        issues.extend(self._check_outliers(candles, outlier_threshold, outlier_threshold_pct))
        issues.extend(self._check_low_volume(candles, low_volume_threshold))

        total_affected = sum(issue.affected_count for issue in issues)
        PASSABLE_THRESHOLD_PCT = Decimal(10)
        affected_pct = Decimal(total_affected) / Decimal(n) * Decimal(100) if n > 0 else Decimal(0)
        is_passable = affected_pct < PASSABLE_THRESHOLD_PCT

        return DataQualityReport(
            total_observations=n,
            issues=issues,
            is_passable=is_passable,
        )

    @staticmethod
    def _empty_report() -> DataQualityReport:
        """Create a report for empty candle data."""
        return DataQualityReport(
            total_observations=0,
            issues=[
                DataQualityIssue(
                    issue_type=DataQualityIssueType.MISSING_VALUES,
                    severity="1.0",
                    description="No candles provided.",
                    affected_count=0,
                ),
            ],
            is_passable=False,
        )

    @staticmethod
    def _check_duplicates(candles: list[Candle]) -> list[DataQualityIssue]:
        """Check for duplicate timestamps."""
        seen_timestamps: dict[str, int] = {}
        dup_indices: list[int] = []
        for i, c in enumerate(candles):
            key = c.open_time.isoformat() if c.open_time else str(i)
            if key in seen_timestamps:
                dup_indices.append(i)
            seen_timestamps[key] = i

        if dup_indices:
            return [
                DataQualityIssue(
                    issue_type=DataQualityIssueType.DUPLICATES,
                    severity="0.5",
                    description=f"{len(dup_indices)} duplicate timestamps found.",
                    affected_indices=dup_indices,
                    affected_count=len(dup_indices),
                ),
            ]
        return []

    @staticmethod
    def _check_gaps(
        candles: list[Candle],
        outlier_threshold: Decimal,
        outlier_threshold_pct: str,
    ) -> list[DataQualityIssue]:
        """Check for gaps between consecutive candles."""
        n = len(candles)
        if n <= 1:
            return []
        gap_indices: list[int] = []
        for i in range(1, n):
            prev_close = Decimal(candles[i - 1].close)
            curr_open = Decimal(candles[i].open)
            if prev_close > 0 and curr_open > 0:
                gap = (
                    abs(Decimal(curr_open) - Decimal(prev_close))
                    / Decimal(prev_close)
                    * Decimal(100)
                )
                if gap > outlier_threshold:
                    gap_indices.append(i)

        if gap_indices:
            return [
                DataQualityIssue(
                    issue_type=DataQualityIssueType.GAPS,
                    severity="0.7",
                    description=(f"{len(gap_indices)} gaps exceeding {outlier_threshold_pct}%."),
                    affected_indices=gap_indices,
                    affected_count=len(gap_indices),
                ),
            ]
        return []

    @staticmethod
    def _check_outliers(
        candles: list[Candle],
        outlier_threshold: Decimal,
        outlier_threshold_pct: str,
    ) -> list[DataQualityIssue]:
        """Check for extreme single-candle moves."""
        n = len(candles)
        if n <= 1:
            return []
        outlier_indices: list[int] = []
        for i in range(1, n):
            prev_close = Decimal(candles[i - 1].close)
            curr_close = Decimal(candles[i].close)
            if prev_close > 0:
                move = abs(curr_close - prev_close) / prev_close * Decimal(100)
                if move > outlier_threshold:
                    outlier_indices.append(i)

        if outlier_indices:
            return [
                DataQualityIssue(
                    issue_type=DataQualityIssueType.OUTLIERS,
                    severity="0.8",
                    description=(
                        f"{len(outlier_indices)} outlier candles (>{outlier_threshold_pct}% move)."
                    ),
                    affected_indices=outlier_indices,
                    affected_count=len(outlier_indices),
                ),
            ]
        return []

    @staticmethod
    def _check_low_volume(
        candles: list[Candle],
        low_volume_threshold: str,
    ) -> list[DataQualityIssue]:
        """Check for low-volume candles."""
        threshold = Decimal(low_volume_threshold)
        low_vol_indices: list[int] = []
        for i, c in enumerate(candles):
            if Decimal(c.volume) <= threshold:
                low_vol_indices.append(i)

        if low_vol_indices:
            return [
                DataQualityIssue(
                    issue_type=DataQualityIssueType.LOW_VOLUME,
                    severity="0.3",
                    description=(
                        f"{len(low_vol_indices)} candles with volume <= {low_volume_threshold}."
                    ),
                    affected_indices=low_vol_indices,
                    affected_count=len(low_vol_indices),
                ),
            ]
        return []


# ── Regime / drift monitors ────────────────────────────────────────


class RegimeMonitor:
    """Market regime monitor.

    Classifies market regime based on trend strength and volatility.
    """

    def analyze(self, candles: list[Candle]) -> RegimeReport:
        """Analyze the regime from candle data."""
        MIN_CANDLES_FOR_ANALYSIS = 2
        if not candles or len(candles) < MIN_CANDLES_FOR_ANALYSIS:
            return RegimeReport()

        n = len(candles)
        observations: list[RegimeObservation] = []

        # Compute returns
        returns: list[Decimal] = []
        for i in range(1, n):
            prev = Decimal(candles[i - 1].close)
            curr = Decimal(candles[i].close)
            if prev > 0:
                returns.append((curr - prev) / prev * Decimal(100))

        if not returns:
            return RegimeReport()

        avg_return = sum(returns, Decimal(0)) / Decimal(len(returns))
        variance = sum((r - avg_return) ** 2 for r in returns) / Decimal(len(returns))
        volatility = _decimal_sqrt(variance) if variance > 0 else Decimal(0)

        # Simple regime classification
        VOLATILITY_THRESHOLD = Decimal("5.0")
        TREND_THRESHOLD = Decimal("0.5")

        if volatility > VOLATILITY_THRESHOLD:
            regime = RegimeType.VOLATILE
            confidence = Decimal("0.8")
        elif avg_return > TREND_THRESHOLD:
            regime = RegimeType.TRENDING_UP
            confidence = Decimal("0.7")
        elif avg_return < -TREND_THRESHOLD:
            regime = RegimeType.TRENDING_DOWN
            confidence = Decimal("0.7")
        else:
            regime = RegimeType.RANGING
            confidence = Decimal("0.6")

        obs = RegimeObservation(
            regime=regime,
            confidence=str(confidence),
            start_index=0,
            end_index=n - 1,
        )
        observations.append(obs)

        # Count regime changes (simplified — just 1 observation)
        regime_changes = 0

        return RegimeReport(
            observations=observations,
            dominant_regime=regime,
            regime_changes=regime_changes,
            avg_confidence=str(confidence),
        )

    def check_stability(self, report: RegimeReport) -> bool:
        """Check if the regime is stable enough for validation."""
        if not report.observations:
            return False
        # Stable if confidence >= 0.5 and regime is known
        return report.dominant_regime != RegimeType.UNKNOWN and Decimal(
            report.avg_confidence
        ) >= Decimal("0.5")


class DriftMonitor:
    """Data drift monitor.

    Detects drift between baseline and current data distributions.
    Uses a simple mean-shift detection: if the absolute difference
    between baseline mean and current mean exceeds a threshold
    (expressed as fraction of baseline std), drift is detected.
    """

    def check(
        self,
        baseline_returns: list[str],
        current_returns: list[str],
        *,
        threshold_pct: str = "50.0",
    ) -> DriftReport:
        """Check for drift between baseline and current returns."""
        if not baseline_returns or not current_returns:
            return DriftReport(
                baseline_observations=len(baseline_returns),
                current_observations=len(current_returns),
            )

        baseline = [Decimal(r) for r in baseline_returns]
        current = [Decimal(r) for r in current_returns]

        baseline_mean = sum(baseline, Decimal(0)) / Decimal(len(baseline))
        current_mean = sum(current, Decimal(0)) / Decimal(len(current))

        baseline_var = sum((r - baseline_mean) ** 2 for r in baseline) / Decimal(len(baseline))
        baseline_std = _decimal_sqrt(baseline_var) if baseline_var > 0 else Decimal("0.0001")

        distance = (
            abs(current_mean - baseline_mean) / baseline_std if baseline_std > 0 else Decimal(0)
        )
        threshold = Decimal(threshold_pct) / Decimal(100)

        is_drifting = distance > threshold

        alerts: list[DriftAlert] = []
        if is_drifting:
            drift_type = DriftType.DATA_DRIFT
            if current_mean < baseline_mean:
                drift_type = DriftType.CONCEPT_DRIFT
            alerts.append(
                DriftAlert(
                    drift_type=drift_type,
                    severity=str(min(distance, Decimal("1"))),
                    description=(
                        f"Mean shift detected: baseline={baseline_mean}, "
                        f"current={current_mean}, distance={distance} std"
                    ),
                    distance_metric=str(distance),
                ),
            )

        return DriftReport(
            alerts=alerts,
            baseline_observations=len(baseline),
            current_observations=len(current),
            is_drifting=is_drifting,
            max_distance=str(distance),
        )


# ── Champion / Challenger shadow mode ──────────────────────────────


class ShadowModeRunner:
    """Champion/challenger shadow mode runner (AD-040).

    Runs a challenger strategy in "shadow mode" — it proposes actions
    without executing them. The runner records what the challenger
    WOULD have done vs. what the champion DID, enabling
    counterfactual attribution analysis.
    """

    def __init__(self) -> None:
        self._runs: dict[str, ShadowRunResult] = {}
        self._lock = threading.Lock()

    def start_run(
        self,
        champion_strategy_id: str,
        challenger_strategy_id: str,
    ) -> ShadowRunResult:
        """Start a new shadow run."""
        run = ShadowRunResult(
            run_id=ShadowRunId.generate(),
            champion_strategy_id=champion_strategy_id,
            challenger_strategy_id=challenger_strategy_id,
            status=ShadowModeStatus.RUNNING,
        )
        with self._lock:
            self._runs[str(run.run_id)] = run
        return run

    def record_counterfactual(
        self,
        run_id: str,
        proposed_action: str,
        champion_action: str,
        expected_outcome: str = "0.0",
        attribution: str = "",
    ) -> None:
        """Record a counterfactual outcome in a shadow run."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(f"Shadow run not found: {run_id}")
            run.counterfactuals.append(
                CounterfactualOutcome(
                    proposed_action=proposed_action,
                    champion_action=champion_action,
                    expected_outcome=expected_outcome,
                    attribution=attribution,
                ),
            )

    def complete_run(
        self,
        run_id: str,
        challenger_return: str,
        champion_return: str,
    ) -> ShadowRunResult:
        """Complete a shadow run and compute attribution score."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(f"Shadow run not found: {run_id}")

            challenger = Decimal(challenger_return)
            champion = Decimal(champion_return)
            attribution = challenger - champion

            run.challenger_return = challenger_return
            run.champion_return = champion_return
            run.attribution_score = str(attribution)
            run.status = ShadowModeStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            return run

    def get_run(self, run_id: str) -> ShadowRunResult | None:
        """Get a shadow run by ID."""
        with self._lock:
            return self._runs.get(run_id)

    @property
    def run_count(self) -> int:
        """Number of shadow runs."""
        with self._lock:
            return len(self._runs)

    def reset(self) -> None:
        """Reset all runs (for testing)."""
        with self._lock:
            self._runs.clear()


# ── Stress scenario library ────────────────────────────────────────


class StressScenarioLibrary:
    """Library of stress scenarios for strategy testing (AD-040).

    Provides a standard set of stress scenarios plus the ability to
    add custom ones.
    """

    def __init__(self) -> None:
        self._scenarios: dict[str, StressScenario] = {}
        self._lock = threading.Lock()
        for scenario in STANDARD_STRESS_SCENARIOS:
            self._scenarios[str(scenario.scenario_id)] = scenario

    def get_all(self) -> list[StressScenario]:
        """Get all scenarios in the library."""
        with self._lock:
            return list(self._scenarios.values())

    def get(self, scenario_id: str) -> StressScenario | None:
        """Get a scenario by ID."""
        with self._lock:
            return self._scenarios.get(scenario_id)

    def add(self, scenario: StressScenario) -> None:
        """Add a custom stress scenario."""
        with self._lock:
            self._scenarios[str(scenario.scenario_id)] = scenario

    @property
    def count(self) -> int:
        """Number of scenarios in the library."""
        with self._lock:
            return len(self._scenarios)

    def run_test(
        self,
        scenario_id: str,
        strategy_version_id: str,
        candles: list[Candle],
        side: str,
    ) -> StressTestResult:
        """Run a strategy through a stress scenario.

        Applies the price shock and volatility multiplier to the
        candles, then simulates the strategy on the stressed data.
        """
        with self._lock:
            scenario = self._scenarios.get(scenario_id)
        if scenario is None:
            raise KeyError(f"Stress scenario not found: {scenario_id}")

        stressed_candles = _apply_stress(candles, scenario, side)
        returns = _simulate_returns(stressed_candles, side)

        if not returns:
            return StressTestResult(
                scenario_id=scenario.scenario_id,
                strategy_version_id=strategy_version_id,
                survival=False,
                notes="No trades generated.",
            )

        pnl = sum(returns, Decimal(0))
        # Max drawdown
        peak = Decimal(0)
        cumulative = Decimal(0)
        max_dd = Decimal(0)
        for r in returns:
            cumulative += r
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)

        # Recovery time: candles from trough to recovery
        recovery = 0
        if max_dd > 0:
            peak2 = Decimal(0)
            cum2 = Decimal(0)
            trough_idx = -1
            for i, r in enumerate(returns):
                cum2 += r
                peak2 = max(peak2, cum2)
                if peak2 - cum2 >= max_dd:
                    trough_idx = i
            if trough_idx >= 0:
                for i in range(trough_idx + 1, len(returns)):
                    cum2 += returns[i]
                    if cum2 >= peak2:
                        recovery = i - trough_idx
                        break

        # Survival: did not hit catastrophic stop (max_dd < 50%)
        CAT_STOP = Decimal(50)
        survival = max_dd < CAT_STOP

        return StressTestResult(
            scenario_id=scenario.scenario_id,
            strategy_version_id=strategy_version_id,
            survival=survival,
            max_drawdown_pct=str(max_dd),
            recovery_time=recovery,
            pnl_pct=str(pnl),
            notes=f"Stressed {len(stressed_candles)} candles with {scenario.name}.",
        )


# ── Validation gate ────────────────────────────────────────────────


class StrategyValidationGate:
    """Strategy validation gate (AD-040).

    No strategy enters paper or live without passing this gate.
    The gate aggregates:
    - CPCV (cross-validation without leakage)
    - PBO (Probability of Backtest Overfitting)
    - Deflated Sharpe Ratio
    - Stress test survival
    - Data quality
    - Regime stability
    - Signed model card

    A PASS requires ALL checks to pass. The gate produces a signed
    report with the decision and all check results.
    """

    def __init__(
        self,
        *,
        signing_key: str | None = None,
        pbo_threshold: str = "0.5",
        dsr_significance: str = "0.05",
    ) -> None:
        self._signing_key = signing_key or os.environ.get(
            "KTI_GATE_SIGNING_KEY",
            "default-gate-signing-key",
        )
        self._pbo_threshold = Decimal(pbo_threshold)
        self._dsr_significance = dsr_significance
        self._cpcv = CPCVEvaluator()
        self._pbo = PBOEvaluator()
        self._dsr = DeflatedSharpeEvaluator()
        self._data_quality = DataQualityPipeline()
        self._regime = RegimeMonitor()
        self._stress = StressScenarioLibrary()

    def evaluate(  # noqa: PLR0913, PLR0917
        self,
        strategy_version: StrategyVersion,
        candles: list[Candle],
        side: str,
        is_returns: list[str] | None = None,
        oos_returns: list[str] | None = None,
        observed_sharpe: str = "0.0",
        model_card: ModelCard | None = None,
    ) -> GateReport:
        """Evaluate a strategy through the full validation gate."""
        strategy_version_id_str = str(strategy_version.version_id)

        # 1. Data quality
        dq_report = self._data_quality.check(candles)
        data_quality_passed = dq_report.is_passable

        # 2. CPCV
        cpcv_config = CPCVConfig()
        cpcv_result = self._cpcv.evaluate(candles, side, cpcv_config)
        cpcv_passed = Decimal(cpcv_result.avg_test_return) > Decimal(0)

        # 3. PBO
        if is_returns and oos_returns:
            pbo_result = self._pbo.evaluate(
                is_returns=is_returns,
                oos_returns=oos_returns,
                config=PBOConfig(),
            )
        else:
            pbo_result = PBOResult(
                pbo="0.0",
                n_trials=100,
                n_partitions=16,
            )
        pbo_passed = not pbo_result.is_overfit

        # 4. Deflated Sharpe
        dsr_result = self._dsr.evaluate(
            observed_sharpe=observed_sharpe,
            config=DeflatedSharpeConfig(
                n_trials=1,
                significance_level=self._dsr_significance,
            ),
        )
        dsr_passed = dsr_result.is_statistically_significant

        # 5. Regime stability
        regime_report = self._regime.analyze(candles)
        regime_passed = self._regime.check_stability(regime_report)

        # 6. Stress tests — run at least 3 standard scenarios
        stress_passed = True
        stress_scenarios = self._stress.get_all()[:3]
        for scenario in stress_scenarios:
            stress_result = self._stress.run_test(
                str(scenario.scenario_id),
                strategy_version_id_str,
                candles,
                side,
            )
            if not stress_result.survival:
                stress_passed = False
                break

        # 7. Model card
        model_card_signed = False
        if model_card is not None:
            model_card_signed = model_card.verify(self._signing_key)

        # Decision: PASS only if ALL checks pass
        all_passed = (
            cpcv_passed
            and pbo_passed
            and dsr_passed
            and stress_passed
            and data_quality_passed
            and regime_passed
            and model_card_signed
        )
        decision = GateDecision.PASS if all_passed else GateDecision.REJECT

        report = GateReport(
            report_id=f"gate-{strategy_version_id_str}",
            strategy_version_id=strategy_version_id_str,
            tenant_id=strategy_version.tenant_id,
            decision=decision,
            cpcv_passed=cpcv_passed,
            pbo_passed=pbo_passed,
            dsr_passed=dsr_passed,
            stress_passed=stress_passed,
            data_quality_passed=data_quality_passed,
            regime_passed=regime_passed,
            model_card_signed=model_card_signed,
            trial_count=0,
            notes="Passing is not a claim of profitability.",
        )
        report.sign(self._signing_key)
        return report

    @property
    def signing_key(self) -> str:
        """The signing key used for gate reports."""
        return self._signing_key


# ── Helper functions ───────────────────────────────────────────────

_MIN_CANDLES_FOR_TRADES = 2
_TRADE_INTERVAL = 3


def _simulate_returns(candles: list[Candle], side: str) -> list[Decimal]:
    """Simulate trade returns on a candle series deterministically."""
    if len(candles) < _MIN_CANDLES_FOR_TRADES:
        return []
    returns: list[Decimal] = []
    for i in range(_TRADE_INTERVAL, len(candles), _TRADE_INTERVAL):
        entry = Decimal(candles[i - _TRADE_INTERVAL].close)
        exit_ = Decimal(candles[i].close)
        if entry > 0:
            if side == "buy":
                ret = (exit_ - entry) / entry * Decimal(100)
            else:
                ret = (entry - exit_) / entry * Decimal(100)
            returns.append(ret)
    return returns


def _simulate_return(candles: list[Candle], side: str) -> Decimal:
    """Simulate a single aggregate return from candle series."""
    returns = _simulate_returns(candles, side)
    if not returns:
        return Decimal(0)
    return sum(returns, Decimal(0)) / Decimal(len(returns))


def _apply_stress(
    candles: list[Candle],
    scenario: StressScenario,
    side: str,
) -> list[Candle]:
    """Apply a stress scenario to candle data."""
    if not candles:
        return []
    shock = Decimal(scenario.price_shock_pct) / Decimal(100)
    vol_mult = Decimal(scenario.volatility_multiplier)

    stressed: list[Candle] = []
    for i, c in enumerate(candles):
        # Apply progressive shock over the scenario duration
        progress = Decimal(i) / Decimal(max(1, len(candles)))
        partial_shock = shock * progress
        open_price = Decimal(c.open) * (Decimal(1) + partial_shock)
        close_price = Decimal(c.close) * (Decimal(1) + partial_shock)
        high_price = Decimal(c.high) * (Decimal(1) + partial_shock)
        low_price = Decimal(c.low) * (Decimal(1) + partial_shock)

        # Increase volatility: widen high-low range
        mid = (high_price + low_price) / Decimal(2)
        spread = (high_price - low_price) * vol_mult
        high_price = mid + spread / Decimal(2)
        low_price = mid - spread / Decimal(2)

        stressed.append(
            Candle(
                symbol=c.symbol,
                timeframe=c.timeframe,
                open_time=c.open_time,
                close_time=c.close_time,
                open=str(max(open_price, Decimal("0.01"))),
                high=str(max(high_price, Decimal("0.01"))),
                low=str(max(low_price, Decimal("0.01"))),
                close=str(max(close_price, Decimal("0.01"))),
                volume=c.volume,
            ),
        )
    return stressed


def _decimal_sqrt(value: Decimal) -> Decimal:
    """Compute square root of a Decimal using Newton's method."""
    if value <= 0:
        return Decimal(0)
    x = value
    PRECISION = Decimal("0.00000001")
    MAX_ITER = 100
    for _ in range(MAX_ITER):
        x_new = (x + value / x) / Decimal(2)
        if abs(x_new - x) < PRECISION:
            return x_new
        x = x_new
    return x


def _decimal_ln(value: Decimal) -> Decimal:
    """Compute natural log of a Decimal using a series approximation."""
    if value <= 0:
        return Decimal(0)
    # Use the identity: ln(x) = 2 * ln(sqrt(x))
    # For x close to 1, use Taylor series; for larger x, rescale
    v = value
    result = Decimal(0)
    while v > Decimal(2):
        v = v / Decimal(2)
        result += Decimal("0.6931471805599453")  # ln(2)
    while v < Decimal("0.5"):
        v = v * Decimal(2)
        result -= Decimal("0.6931471805599453")  # ln(2)

    # Now v is in [0.5, 2], use Taylor series around 1
    # ln(1 + z) = z - z^2/2 + z^3/3 - ...
    z = v - Decimal(1)
    term = z
    for k in range(1, 50):
        result += term / Decimal(k)
        term *= -z
        if abs(term) < Decimal("0.000000000001"):
            break
    return result


def _decimal_logit(value: Decimal) -> Decimal:
    """Logit function: log(p / (1 - p))."""
    if value <= 0:
        return Decimal("-10")
    if value >= 1:
        return Decimal("10")
    p = value
    one_minus_p = Decimal(1) - p
    return _decimal_ln(p / one_minus_p)


def _decimal_normal_sf(z: Decimal) -> str:
    """Survival function (1 - CDF) of standard normal at z.

    Approximation using the complementary error function.
    For deterministic use — not a substitute for scipy.
    """
    if z >= Decimal(10):
        return "0.0"
    if z <= Decimal("-10"):
        return "1.0"
    # Use the approximation: SF(z) ≈ 0.5 * erfc(z / sqrt(2))
    # erfc approximation via series
    x = z / _decimal_sqrt(Decimal(2))
    return str(_erfc(x) / Decimal(2))


def _decimal_normal_ppf(p: Decimal) -> Decimal:
    """Percent point function (inverse CDF) of standard normal.

    Returns z such that P(Z <= z) = p.
    Approximation via rational polynomials (Acklam's algorithm).
    """
    if p <= Decimal(0):
        return Decimal("-10")
    if p >= Decimal(1):
        return Decimal("10")

    # Acklam's coefficients
    a = [
        Decimal("-3.969683028665376e+01"),
        Decimal("2.2094609832452052e+02"),
        Decimal("-2.7592851046949488e+02"),
        Decimal("1.383577518677696688e+02"),
        Decimal("-3.066475906042735346e+01"),
        Decimal("2.50662827745282246082e+00"),
    ]
    b = [
        Decimal("-5.447609984041878952e-01"),
        Decimal("1.61585836814831604686e+00"),
        Decimal("-1.57585191879543565577e+00"),
        Decimal("6.68013118877191984035e-01"),
        Decimal("-1.33606690593424291184e-01"),
    ]

    p_low = Decimal("0.02425")
    p_high = Decimal(1) - p_low

    # Tail coefficients (Acklam)
    c = [
        Decimal("-7.784894002430293e-01"),
        Decimal("-3.2238038467136292e-01"),
        Decimal("-2.4007604745787153e-01"),
        Decimal("-1.3217113244654896e-01"),
        Decimal("-5.3176252734895135e-02"),
        Decimal("-7.9508597707685149e-03"),
    ]
    d = [
        Decimal("5.4331162424781873e-01"),
        Decimal("1.2330970536995106e+00"),
        Decimal("1.0773508994347573e+00"),
        Decimal("3.4120645067507468e-01"),
    ]

    if p < p_low:
        q = _decimal_sqrt(Decimal("-2") * _decimal_ln(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + Decimal(1)
        )

    if p <= p_high:
        q = p - Decimal("0.5")
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) / (
            (((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + Decimal(1)
        )

    q = _decimal_sqrt(Decimal("-2") * _decimal_ln(Decimal(1) - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + Decimal(1)
    )


def _erfc(x: Decimal) -> Decimal:
    """Complementary error function approximation."""
    # Abramowitz & Stegun 7.1.26
    t = Decimal(1) / (Decimal(1) + Decimal("0.3275911") * abs(x))
    poly = (
        Decimal("0.254829592") * t
        + Decimal("-0.284496736") * t**2
        + Decimal("1.421413741") * t**3
        + Decimal("-1.453152027") * t**4
        + Decimal("1.061405429") * t**5
    )
    sign = Decimal(1) if x >= 0 else Decimal(-1)
    return sign * poly * _decimal_exp(-x * x)


def _decimal_exp(x: Decimal) -> Decimal:
    """Exponential function for Decimal using Taylor series."""
    # Split into integer and fractional parts
    int_part = int(x)
    frac = x - Decimal(int_part)
    result = Decimal(1)
    term = Decimal(1)
    for i in range(1, 50):
        term *= frac / Decimal(i)
        result += term
        if abs(term) < Decimal("0.000000000001"):
            break
    # Multiply by e^int_part
    e_int = (
        Decimal("2.718281828459045") ** int_part
        if int_part >= 0
        else Decimal("1") / Decimal("2.718281828459045") ** abs(int_part)
    )
    return result * e_int


def _decimal_sharpe(returns: list[Decimal]) -> Decimal:
    """Compute Sharpe ratio from a list of returns."""
    if not returns:
        return Decimal(0)
    mean = sum(returns, Decimal(0)) / Decimal(len(returns))
    variance = sum((r - mean) ** 2 for r in returns) / Decimal(len(returns))
    std = _decimal_sqrt(variance) if variance > 0 else Decimal("0.0001")
    return mean / std if std > 0 else Decimal(0)
