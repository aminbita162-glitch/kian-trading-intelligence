"""Simulation and truth infrastructure contracts for Kian Trading Intelligence.

Per E5 (Simulation and Truth Infrastructure): deterministic simulation
universe (DST) with multi-seed runs and replay; microstructure-realistic market
twin; adapter conformance suite; snapshot reconciliation; load/chaos drill
contracts; PITR restore with ledger diff.

Per AD-023 (Digital Twin): deterministic simulation, exchange emulation,
replay, fault injection, and repeatable verification before live operations.

Per AD-035 (Evidence-Backed Production Candidate): all verification harnesses
must be separated from the runtime image.

Per Section 01.3: SIMULATION mode uses historical or synthetic data without
real financial orders. No component in this module may enable live trading.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

# ── DST (Deterministic Simulation Universe) ──


class SimulationRunStatus(StrEnum):
    """Status of a DST simulation run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class ReplayStatus(StrEnum):
    """Status of a deterministic replay."""

    PENDING = "pending"
    REPLAYING = "replaying"
    MATCHED = "matched"
    DIVERGED = "diverged"
    FAILED = "failed"


@dataclass(frozen=True)
class SimulationRunId:
    """Stable identity for a DST simulation run."""

    value: UUID

    @classmethod
    def generate(cls) -> SimulationRunId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ReplayId:
    """Stable identity for a deterministic replay."""

    value: UUID

    @classmethod
    def generate(cls) -> ReplayId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SnapshotId:
    """Stable identity for a simulation snapshot."""

    value: UUID

    @classmethod
    def generate(cls) -> SnapshotId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class SimulationSeed:
    """A deterministic seed for reproducible simulation runs.

    Per E5 acceptance: same seed produces identical results.
    The seed is a string hash that drives all pseudo-random state in
    the simulation universe — market data, fills, faults, timing.
    """

    seed: str
    label: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.seed:
            raise ValueError("seed must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    @property
    def hash(self) -> str:
        """SHA-256 hash of the seed for deterministic state derivation."""
        return hashlib.sha256(self.seed.encode()).hexdigest()

    def derive(self, component: str) -> str:
        """Derive a component-specific sub-seed from this seed.

        Ensures that different components (market data, fills, faults)
        get independent deterministic streams from the same root seed.
        """
        return f"{self.seed}:{component}"


@dataclass
class SimulationRunConfig:
    """Configuration for a DST simulation run.

    Attributes:
        seeds: List of seeds for multi-seed runs.
        num_orders: Number of orders to simulate per seed.
        symbols: Trading symbols to simulate.
        duration_seconds: Simulated time horizon.
        fill_latency_ms: Simulated fill latency.
        partial_fill_probability: Probability of partial fills.
        unknown_outcome_probability: Probability of unknown outcomes.
        fault_injection_enabled: Whether to inject faults.
        max_concurrent_sessions: Maximum concurrent sessions.
    """

    seeds: list[SimulationSeed]
    num_orders: int = 100
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    duration_seconds: int = 3600
    fill_latency_ms: int = 0
    partial_fill_probability: str = "0.0"
    unknown_outcome_probability: str = "0.0"
    fault_injection_enabled: bool = False
    max_concurrent_sessions: int = 1

    def __post_init__(self) -> None:
        if not self.seeds:
            raise ValueError("seeds must not be empty.")
        if self.num_orders < 1:
            raise ValueError("num_orders must be >= 1.")
        if self.duration_seconds < 1:
            raise ValueError("duration_seconds must be >= 1.")
        if self.max_concurrent_sessions < 1:
            raise ValueError("max_concurrent_sessions must be >= 1.")
        if Decimal(self.partial_fill_probability) < 0:
            raise ValueError("partial_fill_probability must be >= 0.")
        if Decimal(self.partial_fill_probability) > 1:
            raise ValueError("partial_fill_probability must be <= 1.")
        if Decimal(self.unknown_outcome_probability) < 0:
            raise ValueError("unknown_outcome_probability must be >= 0.")
        if Decimal(self.unknown_outcome_probability) > 1:
            raise ValueError("unknown_outcome_probability must be <= 1.")


@dataclass
class SimulationRunResult:
    """Result of a DST simulation run for a single seed.

    Per E5 acceptance: same seed produces identical results.
    The result is deterministic — running the same seed twice yields
    byte-identical outputs (same orders, same fills, same state transitions).
    """

    run_id: SimulationRunId
    seed: SimulationSeed
    status: SimulationRunStatus
    orders_executed: int = 0
    fills_recorded: int = 0
    state_transitions: int = 0
    faults_injected: int = 0
    duration_ms: int = 0
    output_hash: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error: str = ""

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware (UTC).")


@dataclass
class MultiSeedRunResult:
    """Aggregated result of a multi-seed DST run.

    Per E5: nightly multi-seed runs. Each seed produces an independent
    SimulationRunResult. The aggregate verifies determinism: same seed →
    same output_hash.
    """

    run_results: list[SimulationRunResult]
    total_orders: int = 0
    total_fills: int = 0
    total_faults: int = 0
    all_completed: bool = False
    determinism_verified: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware (UTC).")


# ── Microstructure Market Twin ──


class MicrostructureModel(StrEnum):
    """Market microstructure model for the market twin.

    Per E5: microstructure-realistic market twin.
    """

    RANDOM_WALK = "random_walk"
    MEAN_REVERSION = "mean_reversion"
    ORNSTEIN_UHLENBECK = "ornstein_uhlenbeck"
    VOLUME_WEIGHTED = "volume_weighted"


@dataclass
class MarketTwinConfig:
    """Configuration for the microstructure-realistic market twin.

    Per E5: microstructure-realistic market twin that generates
    realistic price paths, order book dynamics, and trade flow
    from a deterministic seed.

    Attributes:
        seed: Root deterministic seed.
        model: Microstructure model type.
        initial_price: Starting price for the symbol.
        volatility: Per-step volatility (sigma).
        drift: Per-step drift (mu).
        mean_reversion_rate: Mean reversion speed (kappa).
        tick_size: Minimum price increment.
        base_volume: Base trade volume.
        spread_bps: Spread in basis points.
    """

    seed: str
    model: MicrostructureModel = MicrostructureModel.RANDOM_WALK
    initial_price: str = "50000.0"
    volatility: str = "0.02"
    drift: str = "0.0"
    mean_reversion_rate: str = "0.1"
    tick_size: str = "0.01"
    base_volume: str = "100.0"
    spread_bps: str = "2.0"

    def __post_init__(self) -> None:
        if not self.seed:
            raise ValueError("seed must not be empty.")
        if Decimal(self.initial_price) <= 0:
            raise ValueError("initial_price must be positive.")
        if Decimal(self.volatility) < 0:
            raise ValueError("volatility must be >= 0.")
        if Decimal(self.tick_size) <= 0:
            raise ValueError("tick_size must be positive.")
        if Decimal(self.base_volume) <= 0:
            raise ValueError("base_volume must be positive.")
        if Decimal(self.spread_bps) < 0:
            raise ValueError("spread_bps must be >= 0.")


@dataclass
class MarketTwinStep:
    """A single step in the market twin simulation.

    Represents the market state at one time step — price, bid/ask,
    volume, and trade flow. Deterministic from the seed + step index.
    """

    step_index: int
    mid_price: str
    bid_price: str
    ask_price: str
    volume: str
    trade_side: str  # "buy" or "sell"
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.step_index < 0:
            raise ValueError("step_index must be >= 0.")
        if self.trade_side not in ("buy", "sell"):
            raise ValueError(f"Invalid trade_side: {self.trade_side!r}.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if Decimal(self.mid_price) <= 0:
            raise ValueError("mid_price must be positive.")
        if Decimal(self.bid_price) <= 0:
            raise ValueError("bid_price must be positive.")
        if Decimal(self.ask_price) <= 0:
            raise ValueError("ask_price must be positive.")
        if Decimal(self.bid_price) > Decimal(self.ask_price):
            raise ValueError("bid_price must be <= ask_price.")


# ── Adapter Conformance Suite ──


class ConformanceCheckType(StrEnum):
    """Types of adapter conformance checks.

    Per E5: adapter conformance suite verifies that any adapter
    implementing the ExchangeAdapter protocol behaves correctly.
    """

    IDEMPOTENT_SUBMISSION = "idempotent_submission"
    PARTIAL_FILL_HANDLING = "partial_fill_handling"
    CANCEL_IS_IDEMPOTENT = "cancel_is_idempotent"
    RECONCILE_UNKNOWN_OUTCOME = "reconcile_unknown_outcome"
    NO_BLIND_RETRY = "no_blind_retry"
    ORDER_STATE_TRANSITIONS = "order_state_transitions"
    TENANT_ISOLATION = "tenant_isolation"
    CONNECTION_LIFECYCLE = "connection_lifecycle"
    RATE_LIMIT_ENFORCEMENT = "rate_limit_enforcement"


class ConformanceStatus(StrEnum):
    """Status of a conformance check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ConformanceCheckId:
    """Stable identity for a conformance check."""

    value: UUID

    @classmethod
    def generate(cls) -> ConformanceCheckId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class ConformanceResult:
    """Result of a single adapter conformance check.

    Per E5: the conformance suite verifies that any exchange adapter
    implementing the ExchangeAdapter protocol conforms to the required
    behavioral invariants.
    """

    check_id: ConformanceCheckId
    check_type: ConformanceCheckType
    status: ConformanceStatus
    adapter_name: str
    detail: str = ""
    duration_ms: int = 0
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None:
            raise ValueError("checked_at must be timezone-aware (UTC).")


@dataclass
class ConformanceSuiteResult:
    """Result of running the full adapter conformance suite.

    All checks must pass for the adapter to be conformant.
    """

    adapter_name: str
    results: list[ConformanceResult]
    all_passed: bool = False
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None:
            raise ValueError("checked_at must be timezone-aware (UTC).")
        self.total_checks = len(self.results)
        self.passed = sum(1 for r in self.results if r.status is ConformanceStatus.PASSED)
        self.failed = sum(1 for r in self.results if r.status is ConformanceStatus.FAILED)
        self.skipped = sum(1 for r in self.results if r.status is ConformanceStatus.SKIPPED)
        self.all_passed = self.failed == 0 and self.passed > 0


# ── Snapshot Reconciliation ──


class SnapshotStatus(StrEnum):
    """Status of a snapshot reconciliation."""

    MATCHED = "matched"
    DISCREPANCY = "discrepancy"
    RESOLVED = "resolved"
    FAILED = "failed"


@dataclass
class SimulationSnapshot:
    """A point-in-time snapshot of simulation state.

    Per E5: snapshot reconciliation — capture the state of the
    simulation at a checkpoint and reconcile it against a replay
    to detect divergence.

    Attributes:
        snapshot_id: Stable unique identifier.
        seed: Seed that produced this snapshot.
        step_index: Step index when the snapshot was taken.
        ledger_balances: Serialised ledger balances per asset.
        order_states: Serialised order states (client_id → state).
        exposure: Current exposure value.
        timestamp: UTC snapshot timestamp.
        state_hash: SHA-256 hash of the serialised state.
    """

    snapshot_id: SnapshotId
    seed: str
    step_index: int
    ledger_balances: dict[str, str] = field(default_factory=dict)
    order_states: dict[str, str] = field(default_factory=dict)
    exposure: str = "0"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    state_hash: str = ""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")
        if self.step_index < 0:
            raise ValueError("step_index must be >= 0.")


@dataclass
class SnapshotReconciliationResult:
    """Result of reconciling two snapshots.

    Per E5: snapshot reconciliation detects divergence between
    the original run and a replay. A divergence means the simulation
    is non-deterministic — a critical finding.
    """

    original_hash: str
    replay_hash: str
    status: SnapshotStatus
    divergences: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None:
            raise ValueError("checked_at must be timezone-aware (UTC).")

    @property
    def is_match(self) -> bool:
        """True if the snapshots match (same state hash)."""
        return self.original_hash == self.replay_hash


# ── Reality Gap Tracking ──


@dataclass
class RealityGapMetric:
    """A reality gap metric comparing simulation vs real-world behavior.

    Per E5 acceptance: reality gap tracked. The reality gap quantifies
    how far the simulation diverges from real market behavior — this
    is NOT a claim of real-world accuracy, but a measurable delta.
    """

    metric_name: str
    simulated_value: str
    reference_value: str
    gap: str = "0"
    notes: str = ""
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.measured_at.tzinfo is None:
            raise ValueError("measured_at must be timezone-aware (UTC).")
        sim = Decimal(self.simulated_value)
        ref = Decimal(self.reference_value)
        object.__setattr__(self, "gap", str(abs(sim - ref)))


@dataclass
class RealityGapReport:
    """A report of reality gap metrics for a simulation run.

    Per E5 acceptance: reality gap tracked. All metrics are explicitly
    labelled as simulation-vs-reference deltas, NOT claims of real-world
    accuracy.
    """

    seed: str
    metrics: list[RealityGapMetric] = field(default_factory=list)
    total_gap: str = "0"
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware (UTC).")
        if self.metrics:
            total = sum((Decimal(m.gap) for m in self.metrics), Decimal(0))
            object.__setattr__(self, "total_gap", str(total))


# ── Load and Chaos Drill Contracts ──


class DrillType(StrEnum):
    """Type of infrastructure drill.

    Per E5: real load (k6/Locust) and chaos drills in ephemeral
    environments. These contracts model the drill configurations and
    results — the actual load tools run in ephemeral CI environments.
    """

    LOAD_TEST = "load_test"
    CHAOS_FAULT = "chaos_fault"
    NETWORK_PARTITION = "network_partition"
    POD_KILL = "pod_kill"
    LATENCY_INJECTION = "latency_injection"


class DrillStatus(StrEnum):
    """Status of a drill."""

    SCHEDULED = "scheduled"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(frozen=True)
class DrillId:
    """Stable identity for a drill."""

    value: UUID

    @classmethod
    def generate(cls) -> DrillId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class LoadDrillConfig:
    """Configuration for a load test drill.

    Per E5: real load (k6/Locust) in ephemeral environments.
    The config specifies the load profile — virtual users, ramp,
    duration, and target endpoints.
    """

    virtual_users: int = 50
    ramp_up_seconds: int = 10
    duration_seconds: int = 60
    target_endpoint: str = "/health"
    requests_per_second: str = "100.0"
    fail_on_error_pct: str = "1.0"

    def __post_init__(self) -> None:
        if self.virtual_users < 1:
            raise ValueError("virtual_users must be >= 1.")
        if self.ramp_up_seconds < 0:
            raise ValueError("ramp_up_seconds must be >= 0.")
        if self.duration_seconds < 1:
            raise ValueError("duration_seconds must be >= 1.")
        if Decimal(self.requests_per_second) <= 0:
            raise ValueError("requests_per_second must be positive.")
        if Decimal(self.fail_on_error_pct) < 0:
            raise ValueError("fail_on_error_pct must be >= 0.")


@dataclass
class ChaosDrillConfig:
    """Configuration for a chaos fault drill.

    Per E5: chaos drills in ephemeral environments. The config
    specifies the fault type, blast radius, and duration.
    """

    fault_type: DrillType = DrillType.CHAOS_FAULT
    blast_radius_pct: str = "10.0"
    duration_seconds: int = 30
    target_component: str = "exchange-adapter"

    def __post_init__(self) -> None:
        if Decimal(self.blast_radius_pct) <= 0:
            raise ValueError("blast_radius_pct must be positive.")
        BLAST_RADIUS_MAX = Decimal("100")
        if Decimal(self.blast_radius_pct) > BLAST_RADIUS_MAX:
            raise ValueError("blast_radius_pct must be <= 100.")
        if self.duration_seconds < 1:
            raise ValueError("duration_seconds must be >= 1.")


@dataclass
class DrillResult:
    """Result of a load or chaos drill.

    Per E5: performance evidence recorded. The result captures
    throughput, latency, error rate, and pass/fail status.
    """

    drill_id: DrillId
    drill_type: DrillType
    status: DrillStatus
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: str = "0.0"
    p99_latency_ms: str = "0.0"
    error_rate_pct: str = "0.0"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware (UTC).")


# ── PITR (Point-in-Time Restore) with Ledger Diff ──


class PITRStatus(StrEnum):
    """Status of a PITR restore operation."""

    PENDING = "pending"
    RESTORING = "restoring"
    VERIFIED = "verified"
    DIFF_DETECTED = "diff_detected"
    FAILED = "failed"


@dataclass(frozen=True)
class PITRId:
    """Stable identity for a PITR restore."""

    value: UUID

    @classmethod
    def generate(cls) -> PITRId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class PITRConfig:
    """Configuration for a point-in-time restore.

    Per E5: real PITR restore with ledger diff. The restore verifies
    that the ledger can be recovered to a known state and that the
    restored state matches the original (ledger diff = 0).
    """

    restore_point: datetime
    source_snapshot_id: SnapshotId | None = None
    verify_ledger_diff: bool = True

    def __post_init__(self) -> None:
        if self.restore_point.tzinfo is None:
            raise ValueError("restore_point must be timezone-aware (UTC).")


@dataclass
class LedgerDiffEntry:
    """A single difference between original and restored ledger state.

    Per E5: ledger diff — each entry identifies the account, the
    original balance, the restored balance, and the delta.
    """

    account_id: str
    asset: str
    original_balance: str
    restored_balance: str

    def __post_init__(self) -> None:
        if not self.account_id:
            raise ValueError("account_id must not be empty.")
        if not self.asset:
            raise ValueError("asset must not be empty.")

    @property
    def delta(self) -> str:
        """Delta = restored_balance - original_balance."""
        return str(Decimal(self.restored_balance) - Decimal(self.original_balance))

    @property
    def has_diff(self) -> bool:
        """True if the balances differ."""
        return Decimal(self.delta) != 0


@dataclass
class PITRResult:
    """Result of a PITR restore with ledger diff.

    Per E5: real PITR restore with ledger diff. The result includes
    the ledger diff entries — any non-zero delta means the restore
    is imperfect and must be investigated.
    """

    pitr_id: PITRId
    status: PITRStatus
    restore_point: datetime
    ledger_diffs: list[LedgerDiffEntry] = field(default_factory=list)
    total_diff_count: int = 0
    max_abs_delta: str = "0"
    verified: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.restore_point.tzinfo is None:
            raise ValueError("restore_point must be timezone-aware (UTC).")
        self.total_diff_count = sum(1 for d in self.ledger_diffs if d.has_diff)
        if self.ledger_diffs:
            max_delta = max(abs(Decimal(d.delta)) for d in self.ledger_diffs)
            object.__setattr__(self, "max_abs_delta", str(max_delta))
        self.verified = self.status is PITRStatus.VERIFIED and self.total_diff_count == 0


# ── Replay Determinism ──


@dataclass
class ReplayResult:
    """Result of a deterministic replay.

    Per E5: same seed produces identical results. The replay re-runs
    the simulation from a seed and compares the output hash to the
    original run. A match proves determinism; a divergence means
    the simulation is non-deterministic.
    """

    replay_id: ReplayId
    seed: str
    status: ReplayStatus
    original_output_hash: str
    replayed_output_hash: str
    divergences: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware (UTC).")
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware (UTC).")

    @property
    def is_deterministic(self) -> bool:
        """True if the replay matches the original (same output hash)."""
        return self.original_output_hash == self.replayed_output_hash
