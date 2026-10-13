"""Strategy science contracts for Kian Trading Intelligence.

Per E7 (Strategy Science) and AD-040 (Statistical Honesty and Strategy
Validation Gate):

Mandatory pre-registration, trial counter, purged/embargoed CV (CPCV),
Probability of Backtest Overfitting (PBO), Deflated Sharpe Ratio, and signed
model cards. No strategy enters paper or live without passing the gate.

These contracts are leaf-level — they must NOT import from services or
simulation (import-linter contracts-is-leaf).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

# ── Hash-chained trial counter ─────────────────────────────────────


@dataclass(frozen=True)
class TrialId:
    """Stable identity for a validation trial."""

    value: UUID

    @classmethod
    def generate(cls) -> TrialId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ResearchRegistrationId:
    """Stable identity for a pre-registered research entry."""

    value: UUID

    @classmethod
    def generate(cls) -> ResearchRegistrationId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class TrialRecord:
    """A single entry in the hash-chained trial counter.

    Each trial links to the previous trial's hash, forming a tamper-evident
    chain. The hash covers: previous_hash, trial_id, strategy_version_id,
    timestamp, and result_summary.

    Attributes:
        trial_id: Unique trial identifier.
        strategy_version_id: Strategy version under test.
        previous_hash: Hash of the previous trial record (genesis = "genesis").
        timestamp: UTC trial completion timestamp.
        result_summary: JSON-serialisable summary of the trial result.
        trial_hash: SHA-256 hash of this record (computed from the fields above).
    """

    trial_id: TrialId
    strategy_version_id: str
    previous_hash: str = "genesis"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    result_summary: dict[str, Any] = field(default_factory=dict)
    trial_hash: str = ""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if not self.strategy_version_id:
            raise ValueError("strategy_version_id must not be empty.")
        if self.trial_hash == "":
            self.trial_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = {
            "previous_hash": self.previous_hash,
            "trial_id": str(self.trial_id),
            "strategy_version_id": self.strategy_version_id,
            "timestamp": self.timestamp.isoformat(),
            "result_summary": json.dumps(self.result_summary, sort_keys=True),
        }
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify_chain(self, expected_previous_hash: str) -> bool:
        """Verify that this record's previous_hash matches the expected value."""
        return self.previous_hash == expected_previous_hash


# ── Pre-registered research ─────────────────────────────────────────


@dataclass(frozen=True)
class ResearchRegistration:
    """Pre-registered research hypothesis for a strategy (AD-040).

    A strategy must be pre-registered before any validation trial runs.
    Pre-registration locks the hypothesis, intended metrics, and data
    scope before seeing the results — preventing data-snooping.

    Attributes:
        registration_id: Unique registration identifier.
        strategy_version_id: Strategy version being evaluated.
        tenant_id: Tenant scope.
        hypothesis: The pre-registered hypothesis statement.
        intended_metrics: Metrics that will be evaluated.
        data_scope: Description of the data window / scope.
        rejection_criteria: Criteria under which the strategy is rejected.
        registered_at: UTC registration timestamp.
        registration_hash: SHA-256 hash of the registration (immutable lock).
    """

    registration_id: ResearchRegistrationId
    strategy_version_id: str
    tenant_id: str
    hypothesis: str
    intended_metrics: list[str]
    data_scope: str
    rejection_criteria: list[str]
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    registration_hash: str = ""

    def __post_init__(self) -> None:
        if self.registered_at.tzinfo is None:
            raise ValueError("registered_at must be timezone-aware (UTC).")
        if not self.hypothesis:
            raise ValueError("hypothesis must not be empty.")
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if not self.intended_metrics:
            raise ValueError("intended_metrics must not be empty.")
        if self.registration_hash == "":
            object.__setattr__(self, "registration_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        payload = {
            "registration_id": str(self.registration_id),
            "strategy_version_id": self.strategy_version_id,
            "tenant_id": self.tenant_id,
            "hypothesis": self.hypothesis,
            "intended_metrics": list(self.intended_metrics),
            "data_scope": self.data_scope,
            "rejection_criteria": list(self.rejection_criteria),
            "registered_at": self.registered_at.isoformat(),
        }
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── CPCV (Combinatorial Purged Cross-Validation) ────────────────────


class CPCVMode(StrEnum):
    """Mode of CPCV execution."""

    PURGED = "purged"
    EMBARGOED = "embargoed"


@dataclass
class CPCVConfig:
    """Configuration for Combinatorial Purged Cross-Validation (CPCV).

    CPCV is a cross-validation scheme that combats overfitting by:
    - Purging: removing observations near training/test boundaries to
      prevent leakage from overlapping labels.
    - Embargoing: adding a buffer after training data to prevent
      serial-correlation leakage.

    Attributes:
        n_groups: Number of groups to split data into.
        n_test_groups: Number of groups held out for testing per fold.
        purge_window: Number of observations to purge near boundaries.
        embargo_pct: Fraction of total data to embargo after training.
        mode: Purged or embargoed (or both).
    """

    n_groups: int = 6
    n_test_groups: int = 2
    purge_window: int = 5
    embargo_pct: str = "0.01"
    mode: CPCVMode = CPCVMode.PURGED

    def __post_init__(self) -> None:
        MIN_GROUPS = 2
        if self.n_groups < MIN_GROUPS:
            raise ValueError("n_groups must be >= 2.")
        if self.n_test_groups < 1:
            raise ValueError("n_test_groups must be >= 1.")
        if self.n_test_groups >= self.n_groups:
            raise ValueError("n_test_groups must be < n_groups.")
        if self.purge_window < 0:
            raise ValueError("purge_window must be non-negative.")
        if Decimal(self.embargo_pct) < Decimal("0") or Decimal(self.embargo_pct) > Decimal("1"):
            raise ValueError("embargo_pct must be in [0, 1].")


@dataclass
class CPCVFold:
    """A single CPCV fold.

    Attributes:
        fold_index: 0-based fold index.
        train_indices: Indices in the training set.
        test_indices: Indices in the test set.
        purged_indices: Indices purged to prevent leakage.
        embargoed_indices: Indices embargoed after training.
    """

    fold_index: int
    train_indices: list[int] = field(default_factory=list)
    test_indices: list[int] = field(default_factory=list)
    purged_indices: list[int] = field(default_factory=list)
    embargoed_indices: list[int] = field(default_factory=list)


@dataclass
class CPCVResult:
    """Result of a CPCV run.

    Attributes:
        config: Configuration used.
        folds: List of CPCV folds.
        fold_returns: Per-fold test returns.
        avg_test_return: Average return across folds.
        return_std: Standard deviation of fold returns.
        avg_sharpe: Average per-fold Sharpe ratio.
        n_obs_total: Total observations in the dataset.
        n_obs_purged: Total purged observations across folds.
        n_obs_embargoed: Total embargoed observations across folds.
    """

    config: CPCVConfig
    folds: list[CPCVFold] = field(default_factory=list)
    fold_returns: list[str] = field(default_factory=list)
    avg_test_return: str = "0.0"
    return_std: str = "0.0"
    avg_sharpe: str = "0.0"
    n_obs_total: int = 0
    n_obs_purged: int = 0
    n_obs_embargoed: int = 0


# ── PBO (Probability of Backtest Overfitting) ───────────────────────


@dataclass
class PBOConfig:
    """Configuration for Probability of Backtest Overfitting (PBO).

    PBO measures the probability that a strategy's performance ranking
    in backtests is NOT preserved out-of-sample. A PBO > 0.5 indicates
    the strategy selection is no better than random — the backtests are
    overfit.

    Attributes:
        n_trials: Number of random parameter trials.
        n_partitions: Number of partitions (IS / OOS split count).
        barrier_type: Type of labeling barrier.
    """

    n_trials: int = 100
    n_partitions: int = 16

    def __post_init__(self) -> None:
        MIN_TRIALS = 8
        MIN_PARTITIONS = 2
        if self.n_trials < MIN_TRIALS:
            raise ValueError("n_trials must be >= 8.")
        if self.n_partitions < MIN_PARTITIONS:
            raise ValueError("n_partitions must be >= 2.")


@dataclass
class PBOResult:
    """Result of a PBO computation.

    Attributes:
        pbo: Probability of Backtest Overfitting (0 to 1).
        logits: Logit-scaled PBO value.
        n_trials: Number of trials used.
        n_partitions: Number of partitions used.
        threshold: PBO threshold above which the strategy is rejected.
        is_overfit: Whether the strategy is overfit (PBO > threshold).
    """

    pbo: str = "0.0"
    logits: str = "0.0"
    n_trials: int = 0
    n_partitions: int = 0
    threshold: str = "0.5"
    is_overfit: bool = False

    @property
    def is_rejected(self) -> bool:
        """True if the strategy is rejected due to overfitting."""
        return self.is_overfit


# ── Deflated Sharpe Ratio ──────────────────────────────────────────


@dataclass
class DeflatedSharpeConfig:
    """Configuration for Deflated Sharpe Ratio (DSR).

    The DSR adjusts the observed Sharpe ratio for: number of trials,
    selection bias, skewness, and observation length. A DSR below a
    threshold indicates the observed Sharpe may be a statistical
    artifact.

    Attributes:
        n_trials: Number of strategy variants tested.
        observation_length: Length of the out-of-sample observation window.
        skewness: Sample skewness of returns.
        kurtosis: Sample kurtosis of returns.
        significance_level: p-value threshold for rejection.
    """

    n_trials: int = 1
    observation_length: int = 252
    skewness: str = "0.0"
    kurtosis: str = "3.0"
    significance_level: str = "0.05"

    def __post_init__(self) -> None:
        MIN_TRIALS = 1
        MIN_OBS_LENGTH = 2
        if self.n_trials < MIN_TRIALS:
            raise ValueError("n_trials must be >= 1.")
        if self.observation_length < MIN_OBS_LENGTH:
            raise ValueError("observation_length must be >= 2.")
        sig = Decimal(self.significance_level)
        if sig <= Decimal("0") or sig >= Decimal("1"):
            raise ValueError("significance_level must be in (0, 1).")


@dataclass
class DeflatedSharpeResult:
    """Result of a Deflated Sharpe Ratio computation.

    Attributes:
        observed_sharpe: The raw observed Sharpe ratio.
        expected_sharpe: Expected maximum Sharpe under the null (no skill).
        deflated_sharpe: The DSR — Sharpe adjusted for selection bias.
        p_value: p-value of the deflated Sharpe.
        is_statistically_significant: Whether DSR is significant.
        threshold: DSR threshold for significance.
    """

    observed_sharpe: str = "0.0"
    expected_sharpe: str = "0.0"
    deflated_sharpe: str = "0.0"
    p_value: str = "0.0"
    is_statistically_significant: bool = False
    threshold: str = "0.0"


# ── Data-quality pipeline ──────────────────────────────────────────


class DataQualityIssueType(StrEnum):
    """Types of data quality issues."""

    MISSING_VALUES = "missing_values"
    OUTLIERS = "outliers"
    DUPLICATES = "duplicates"
    GAPS = "gaps"
    STALE = "stale"
    LOW_VOLUME = "low_volume"
    PRICE_ANOMALY = "price_anomaly"


@dataclass
class DataQualityIssue:
    """A single data quality issue detected by the pipeline.

    Attributes:
        issue_type: Type of issue.
        severity: Severity (0 to 1).
        description: Human-readable description.
        affected_indices: Data indices affected.
        affected_count: Number of affected observations.
    """

    issue_type: DataQualityIssueType
    severity: str = "0.0"
    description: str = ""
    affected_indices: list[int] = field(default_factory=list)
    affected_count: int = 0


@dataclass
class DataQualityReport:
    """Report from the data-quality pipeline.

    Attributes:
        total_observations: Total observations checked.
        issues: List of detected issues.
        is_passable: Whether the data is clean enough for validation.
        checked_at: UTC report timestamp.
    """

    total_observations: int = 0
    issues: list[DataQualityIssue] = field(default_factory=list)
    is_passable: bool = True
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None:
            raise ValueError("checked_at must be timezone-aware (UTC).")

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def total_affected(self) -> int:
        return sum(issue.affected_count for issue in self.issues)

    @property
    def affected_pct(self) -> str:
        if self.total_observations == 0:
            return "0.0"
        return str(
            Decimal(self.total_affected) / Decimal(self.total_observations) * Decimal(100),
        )


# ── Regime / drift monitors ─────────────────────────────────────────


class RegimeType(StrEnum):
    """Market regime types."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class RegimeObservation:
    """A single regime classification observation.

    Attributes:
        regime: Detected regime type.
        confidence: Confidence (0 to 1).
        start_index: Start index of the regime window.
        end_index: End index of the regime window.
        timestamp: UTC observation timestamp.
    """

    regime: RegimeType
    confidence: str = "0.0"
    start_index: int = 0
    end_index: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class RegimeReport:
    """Report from the regime monitor.

    Attributes:
        observations: List of regime observations.
        dominant_regime: The most frequently observed regime.
        regime_changes: Number of regime transitions.
        avg_confidence: Average confidence across observations.
    """

    observations: list[RegimeObservation] = field(default_factory=list)
    dominant_regime: RegimeType = RegimeType.UNKNOWN
    regime_changes: int = 0
    avg_confidence: str = "0.0"


class DriftType(StrEnum):
    """Types of data drift."""

    CONCEPT_DRIFT = "concept_drift"
    DATA_DRIFT = "data_drift"
    LABEL_DRIFT = "label_drift"
    COVARIATE_DRIFT = "covariate_drift"


@dataclass
class DriftAlert:
    """A single drift alert.

    Attributes:
        drift_type: Type of drift.
        severity: Severity (0 to 1).
        description: Human-readable description.
        detected_at: UTC detection timestamp.
        distance_metric: Distance/score triggering the alert.
    """

    drift_type: DriftType
    severity: str = "0.0"
    description: str = ""
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    distance_metric: str = "0.0"

    def __post_init__(self) -> None:
        if self.detected_at.tzinfo is None:
            raise ValueError("detected_at must be timezone-aware (UTC).")


@dataclass
class DriftReport:
    """Report from the drift monitor.

    Attributes:
        alerts: List of drift alerts.
        baseline_observations: Number of baseline observations.
        current_observations: Number of current observations.
        is_drifting: Whether significant drift is detected.
        max_distance: Maximum distance observed.
    """

    alerts: list[DriftAlert] = field(default_factory=list)
    baseline_observations: int = 0
    current_observations: int = 0
    is_drifting: bool = False
    max_distance: str = "0.0"


# ── Champion / Challenger shadow mode ───────────────────────────────


class ShadowModeStatus(StrEnum):
    """Status of a champion/challenger shadow run."""

    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ShadowRunId:
    """Stable identity for a shadow-mode run."""

    value: UUID

    @classmethod
    def generate(cls) -> ShadowRunId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class CounterfactualOutcome:
    """Counterfactual outcome for a challenger in shadow mode.

    What the challenger WOULD have done if it were the champion.

    Attributes:
        proposed_action: The action the challenger would have taken.
        champion_action: The action the champion actually took.
        expected_outcome: Expected outcome if the challenger action was taken.
        attribution: Attribution of the difference to the challenger's logic.
    """

    proposed_action: str
    champion_action: str
    expected_outcome: str = "0.0"
    attribution: str = ""


@dataclass
class ShadowRunResult:
    """Result of a champion/challenger shadow run.

    Attributes:
        run_id: Unique run identifier.
        champion_strategy_id: Strategy ID of the current champion.
        challenger_strategy_id: Strategy ID of the challenger.
        status: Run status.
        counterfactuals: List of counterfactual outcomes.
        challenger_return: Return the challenger would have achieved.
        champion_return: Return the champion achieved.
        attribution_score: Difference (challenger - champion).
        started_at: UTC start timestamp.
        completed_at: UTC completion timestamp.
    """

    run_id: ShadowRunId
    champion_strategy_id: str
    challenger_strategy_id: str
    status: ShadowModeStatus = ShadowModeStatus.RUNNING
    counterfactuals: list[CounterfactualOutcome] = field(default_factory=list)
    challenger_return: str = "0.0"
    champion_return: str = "0.0"
    attribution_score: str = "0.0"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware (UTC).")


# ── Stress scenario library ─────────────────────────────────────────


class StressScenarioType(StrEnum):
    """Types of stress scenarios."""

    MARKET_CRASH = "market_crash"
    FLASH_CRASH = "flash_crash"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    VOLATILITY_SPIKE = "volatility_spike"
    CORRELATION_BREAKDOWN = "correlation_breakdown"
    BLACK_SWAN = "black_swan"
    INTEREST_RATE_SHOCK = "interest_rate_shock"
    CURRENCY_CRISIS = "currency_crisis"
    REGULATORY_SHOCK = "regulatory_shock"
    CONTAGION = "contagion"
    GAP_RISK = "gap_risk"
    FAT_TAILS = "fat_tails"


@dataclass(frozen=True)
class StressScenarioId:
    """Stable identity for a stress scenario."""

    value: UUID

    @classmethod
    def generate(cls) -> StressScenarioId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class StressScenario:
    """A single stress scenario in the library.

    Attributes:
        scenario_id: Unique scenario identifier.
        name: Human-readable scenario name.
        scenario_type: Type of stress scenario.
        description: Detailed description.
        price_shock_pct: Percentage price shock applied.
        volatility_multiplier: Multiplier applied to volatility.
        duration_candles: Number of candles the scenario lasts.
        parameters: Additional scenario parameters.
    """

    scenario_id: StressScenarioId
    name: str
    scenario_type: StressScenarioType
    description: str = ""
    price_shock_pct: str = "0.0"
    volatility_multiplier: str = "1.0"
    duration_candles: int = 100
    parameters: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty.")
        if self.duration_candles < 1:
            raise ValueError("duration_candles must be >= 1.")


@dataclass
class StressTestResult:
    """Result of running a strategy through a stress scenario.

    Attributes:
        scenario_id: Scenario that was run.
        strategy_version_id: Strategy version tested.
        survival: Whether the strategy survived (did not hit catastrophic stop).
        max_drawdown_pct: Maximum drawdown under stress.
        recovery_time: Candles to recover (if recovered).
        pnl_pct: P&L percentage during the stress window.
        notes: Additional notes.
    """

    scenario_id: StressScenarioId
    strategy_version_id: str
    survival: bool = True
    max_drawdown_pct: str = "0.0"
    recovery_time: int = 0
    pnl_pct: str = "0.0"
    notes: str = ""


# ── Signed model cards ──────────────────────────────────────────────


@dataclass(frozen=True)
class ModelCardId:
    """Stable identity for a signed model card."""

    value: UUID

    @classmethod
    def generate(cls) -> ModelCardId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ModelCard:
    """A signed model card for a strategy (AD-040).

    A model card documents a strategy's intended use, performance
    characteristics, known limitations, and validation results. It is
    cryptographically signed to prevent tampering.

    Attributes:
        card_id: Unique card identifier.
        strategy_version_id: Strategy version this card describes.
        tenant_id: Tenant scope.
        model_name: Human-readable model/strategy name.
        intended_use: Description of intended use.
        performance_summary: Summary of performance metrics.
        known_limitations: Known limitations of the strategy.
        validation_summary: Summary of validation results.
        risk_profile: Risk characteristics (max drawdown, volatility, etc.).
        data_requirements: Data needed for the strategy.
        created_at: UTC creation timestamp.
        signature: HMAC-SHA256 signature over the card content.
    """

    card_id: ModelCardId
    strategy_version_id: str
    tenant_id: str
    model_name: str
    intended_use: str
    performance_summary: dict[str, str] = field(default_factory=dict)
    known_limitations: list[str] = field(default_factory=list)
    validation_summary: dict[str, str] = field(default_factory=dict)
    risk_profile: dict[str, str] = field(default_factory=dict)
    data_requirements: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    signature: str = ""

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if not self.model_name:
            raise ValueError("model_name must not be empty.")
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if not self.strategy_version_id:
            raise ValueError("strategy_version_id must not be empty.")

    def _canonical_payload(self) -> str:
        payload = {
            "card_id": str(self.card_id),
            "strategy_version_id": self.strategy_version_id,
            "tenant_id": self.tenant_id,
            "model_name": self.model_name,
            "intended_use": self.intended_use,
            "performance_summary": dict(self.performance_summary),
            "known_limitations": list(self.known_limitations),
            "validation_summary": dict(self.validation_summary),
            "risk_profile": dict(self.risk_profile),
            "data_requirements": list(self.data_requirements),
            "created_at": self.created_at.isoformat(),
        }
        return json.dumps(payload, sort_keys=True)

    def compute_signature(self, key: str | bytes) -> str:
        """Compute the HMAC-SHA256 signature for this model card."""
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        return hmac.new(
            key_bytes,
            self._canonical_payload().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def sign(self, key: str | bytes) -> None:
        """Sign this model card in-place with the given key."""
        self.signature = self.compute_signature(key)

    def verify(self, key: str | bytes) -> bool:
        """Verify that the model card's signature is valid."""
        if not self.signature:
            return False
        return hmac.compare_digest(self.signature, self.compute_signature(key))


# ── Validation gate report ──────────────────────────────────────────


class GateDecision(StrEnum):
    """Decision of the strategy validation gate."""

    PASS = "pass"
    REJECT = "reject"
    CONDITIONAL = "conditional"


@dataclass
class GateReport:
    """Signed gate report for a strategy (AD-040).

    No strategy enters paper trading without a signed gate report with
    a PASS decision. The report aggregates all validation results:
    CPCV, PBO, Deflated Sharpe, stress tests, data quality, regime
    stability, and the signed model card.

    Attributes:
        report_id: Unique report identifier.
        strategy_version_id: Strategy version evaluated.
        tenant_id: Tenant scope.
        decision: Gate decision (PASS / REJECT / CONDITIONAL).
        cpcv_passed: Whether CPCV validation passed.
        pbo_passed: Whether PBO is acceptable (not overfit).
        dsr_passed: Whether Deflated Sharpe is significant.
        stress_passed: Whether all stress scenarios were survived.
        data_quality_passed: Whether data quality is acceptable.
        regime_passed: Whether regime stability is acceptable.
        model_card_signed: Whether the model card is signed and verified.
        trial_count: Number of trials in the hash-chained counter.
        notes: Additional notes.
        timestamp: UTC report timestamp.
        signature: HMAC-SHA256 signature of the report.
    """

    report_id: str
    strategy_version_id: str
    tenant_id: str
    decision: GateDecision = GateDecision.REJECT
    cpcv_passed: bool = False
    pbo_passed: bool = False
    dsr_passed: bool = False
    stress_passed: bool = False
    data_quality_passed: bool = False
    regime_passed: bool = False
    model_card_signed: bool = False
    trial_count: int = 0
    notes: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    signature: str = ""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if not self.report_id:
            raise ValueError("report_id must not be empty.")

    def _canonical_payload(self) -> str:
        payload = {
            "report_id": self.report_id,
            "strategy_version_id": self.strategy_version_id,
            "tenant_id": self.tenant_id,
            "decision": self.decision.value,
            "cpcv_passed": self.cpcv_passed,
            "pbo_passed": self.pbo_passed,
            "dsr_passed": self.dsr_passed,
            "stress_passed": self.stress_passed,
            "data_quality_passed": self.data_quality_passed,
            "regime_passed": self.regime_passed,
            "model_card_signed": self.model_card_signed,
            "trial_count": self.trial_count,
            "notes": self.notes,
            "timestamp": self.timestamp.isoformat(),
        }
        return json.dumps(payload, sort_keys=True)

    def compute_signature(self, key: str | bytes) -> str:
        """Compute HMAC-SHA256 signature for this gate report."""
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        return hmac.new(
            key_bytes,
            self._canonical_payload().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def sign(self, key: str | bytes) -> None:
        """Sign this gate report in-place with the given key."""
        self.signature = self.compute_signature(key)

    def verify(self, key: str | bytes) -> bool:
        """Verify that the gate report's signature is valid."""
        if not self.signature:
            return False
        return hmac.compare_digest(self.signature, self.compute_signature(key))

    @property
    def is_pass(self) -> bool:
        """True if all gates passed and the decision is PASS."""
        return (
            self.decision is GateDecision.PASS
            and self.cpcv_passed
            and self.pbo_passed
            and self.dsr_passed
            and self.stress_passed
            and self.data_quality_passed
            and self.regime_passed
            and self.model_card_signed
        )

    @property
    def all_checks_passed(self) -> bool:
        """True if all individual checks passed (regardless of decision)."""
        return (
            self.cpcv_passed
            and self.pbo_passed
            and self.dsr_passed
            and self.stress_passed
            and self.data_quality_passed
            and self.regime_passed
            and self.model_card_signed
        )


# ── Standard stress scenario library ────────────────────────────────

STANDARD_STRESS_SCENARIOS: list[StressScenario] = [
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Global Market Crash 2008",
        scenario_type=StressScenarioType.MARKET_CRASH,
        description="Sustained 40%+ decline over 6 months.",
        price_shock_pct="-40.0",
        volatility_multiplier="3.0",
        duration_candles=180,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Flash Crash 2010",
        scenario_type=StressScenarioType.FLASH_CRASH,
        description="Intraday 10% crash and partial recovery within minutes.",
        price_shock_pct="-10.0",
        volatility_multiplier="10.0",
        duration_candles=20,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="COVID Volatility Spike 2020",
        scenario_type=StressScenarioType.VOLATILITY_SPIKE,
        description="3x volatility spike with 30% drawdown over 4 weeks.",
        price_shock_pct="-30.0",
        volatility_multiplier="3.0",
        duration_candles=120,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Liquidity Crisis 2015",
        scenario_type=StressScenarioType.LIQUIDITY_CRISIS,
        description="Bid-ask spreads widen 5x, volume drops 80%.",
        price_shock_pct="-15.0",
        volatility_multiplier="2.5",
        duration_candles=90,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Correlation Breakdown",
        scenario_type=StressScenarioType.CORRELATION_BREAKDOWN,
        description="Historically correlated assets decouple abruptly.",
        price_shock_pct="-20.0",
        volatility_multiplier="2.0",
        duration_candles=60,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Black Swan Event",
        scenario_type=StressScenarioType.BLACK_SWAN,
        description="Unprecedented 50%+ crash with no historical analogue.",
        price_shock_pct="-50.0",
        volatility_multiplier="5.0",
        duration_candles=150,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Interest Rate Shock",
        scenario_type=StressScenarioType.INTEREST_RATE_SHOCK,
        description="Sudden 200bp rate increase.",
        price_shock_pct="-10.0",
        volatility_multiplier="1.5",
        duration_candles=80,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Currency Crisis",
        scenario_type=StressScenarioType.CURRENCY_CRISIS,
        description="Fiat currency devaluation 30%.",
        price_shock_pct="-30.0",
        volatility_multiplier="2.0",
        duration_candles=100,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Regulatory Shock",
        scenario_type=StressScenarioType.REGULATORY_SHOCK,
        description="Sudden ban on crypto trading in major jurisdiction.",
        price_shock_pct="-25.0",
        volatility_multiplier="3.0",
        duration_candles=110,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Contagion",
        scenario_type=StressScenarioType.CONTAGION,
        description="Cross-market contagion: equities, bonds, crypto all fall.",
        price_shock_pct="-35.0",
        volatility_multiplier="2.5",
        duration_candles=130,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Gap Risk",
        scenario_type=StressScenarioType.GAP_RISK,
        description="Weekend gap: 15% overnight decline with no exit possible.",
        price_shock_pct="-15.0",
        volatility_multiplier="4.0",
        duration_candles=10,
    ),
    StressScenario(
        scenario_id=StressScenarioId.generate(),
        name="Fat Tails",
        scenario_type=StressScenarioType.FAT_TAILS,
        description="Sustained extreme moves: 5-sigma daily moves for 2 weeks.",
        price_shock_pct="-20.0",
        volatility_multiplier="5.0",
        duration_candles=42,
    ),
]
