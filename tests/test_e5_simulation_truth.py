"""E5 — Simulation and Truth Infrastructure tests.

Per E5 deliverables:
- Deterministic Simulation Universe (DST) with multi-seed runs and replay
- Microstructure-realistic market twin
- Adapter conformance suite
- Snapshot reconciliation
- Real load (k6/Locust) and chaos drills in ephemeral environments
- Real PITR restore with ledger diff

Acceptance: same seed produces identical results; reality gap tracked;
performance evidence recorded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from simulation.conformance_suite import AdapterConformanceSuite
from simulation.dst_engine import DSTEngine
from simulation.exchange_simulator import ExchangeSimulator
from simulation.load_chaos_drills import (
    ChaosDrillRunner,
    LoadDrillRunner,
)
from simulation.market_twin import MarketTwin
from simulation.reality_gap import RealityGapTracker
from simulation.snapshot_pitr import (
    PITRRestorer,
    SnapshotReconciler,
)

from contracts.market_data import Symbol
from contracts.simulation import (
    ChaosDrillConfig,
    ConformanceStatus,
    DrillStatus,
    DrillType,
    LoadDrillConfig,
    MarketTwinConfig,
    MicrostructureModel,
    PITRConfig,
    PITRStatus,
    SimulationRunConfig,
    SimulationRunStatus,
    SimulationSeed,
    SnapshotStatus,
)

# ── DST Engine Tests ──


class TestDSTEngine:
    """Test the Deterministic Simulation Universe engine."""

    def test_single_seed_run_completes(self) -> None:
        """A single-seed DST run must complete successfully."""
        engine = DSTEngine()
        seed = SimulationSeed(seed="test-seed-1")
        config = SimulationRunConfig(seeds=[seed], num_orders=10)
        result = engine.run_single_seed(config, seed)

        assert result.status is SimulationRunStatus.COMPLETED
        assert result.orders_executed == 10
        assert result.fills_recorded > 0
        assert result.output_hash != ""
        assert result.completed_at is not None
        assert result.error == ""

    def test_same_seed_produces_identical_results(self) -> None:
        """Same seed must produce identical output hash — the core E5 acceptance."""
        engine = DSTEngine()
        seed = SimulationSeed(seed="determinism-test")
        config = SimulationRunConfig(seeds=[seed], num_orders=50)

        result1 = engine.run_single_seed(config, seed)
        result2 = engine.run_single_seed(config, seed)

        assert result1.output_hash == result2.output_hash
        assert result1.orders_executed == result2.orders_executed
        assert result1.fills_recorded == result2.fills_recorded
        assert result1.state_transitions == result2.state_transitions

    def test_different_seeds_produce_different_results(self) -> None:
        """Different seeds should produce different output hashes."""
        engine = DSTEngine()
        seed1 = SimulationSeed(seed="seed-alpha")
        seed2 = SimulationSeed(seed="seed-beta")
        config = SimulationRunConfig(seeds=[seed1, seed2], num_orders=20)

        result1 = engine.run_single_seed(config, seed1)
        result2 = engine.run_single_seed(config, seed2)

        assert result1.output_hash != result2.output_hash

    def test_multi_seed_run(self) -> None:
        """Multi-seed run must complete all seeds and verify determinism."""
        engine = DSTEngine()
        seeds = [SimulationSeed(seed=f"multi-{i}") for i in range(5)]
        config = SimulationRunConfig(seeds=seeds, num_orders=10)

        result = engine.run_multi_seed(config)

        assert result.all_completed is True
        assert len(result.run_results) == 5
        assert result.determinism_verified is True
        assert result.total_orders == 50

    def test_replay_matches_original(self) -> None:
        """Replaying a seed must produce the same output hash as the original."""
        engine = DSTEngine()
        seed = SimulationSeed(seed="replay-test")
        config = SimulationRunConfig(seeds=[seed], num_orders=30)

        original = engine.run_single_seed(config, seed)
        replay = engine.replay_seed(config, seed)

        assert original.output_hash == replay.output_hash

    def test_fault_injection(self) -> None:
        """Fault injection is deterministic from the seed."""
        engine = DSTEngine()
        seed = SimulationSeed(seed="fault-test")
        config = SimulationRunConfig(
            seeds=[seed],
            num_orders=100,
            fault_injection_enabled=True,
        )

        result = engine.run_single_seed(config, seed)
        assert result.faults_injected > 0

        # Same seed → same number of faults
        result2 = engine.run_single_seed(config, seed)
        assert result.faults_injected == result2.faults_injected

    def test_seed_derive_is_deterministic(self) -> None:
        """Seed.derive() produces consistent component seeds."""
        seed = SimulationSeed(seed="derive-test")
        assert seed.derive("market") == "derive-test:market"
        assert seed.derive("fills") == "derive-test:fills"
        assert seed.derive("market") != seed.derive("fills")

    def test_seed_hash_is_stable(self) -> None:
        """Seed.hash is deterministic."""
        seed = SimulationSeed(seed="hash-test")
        h1 = seed.hash
        h2 = seed.hash
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex


# ── Market Twin Tests ──


class TestMarketTwin:
    """Test the microstructure-realistic market twin."""

    def test_generates_positive_prices(self) -> None:
        """Market twin must generate positive prices."""
        config = MarketTwinConfig(seed="mt-test-1")
        twin = MarketTwin(config)

        for _ in range(100):
            step = twin.step()
            assert Decimal(step.mid_price) > 0
            assert Decimal(step.bid_price) > 0
            assert Decimal(step.ask_price) > 0
            assert Decimal(step.bid_price) <= Decimal(step.ask_price)

    def test_deterministic_same_seed(self) -> None:
        """Same seed + same config → same price sequence."""
        config = MarketTwinConfig(seed="determinism-mt")
        twin1 = MarketTwin(config)
        twin2 = MarketTwin(config)

        steps1 = twin1.generate_steps(50)
        steps2 = twin2.generate_steps(50)

        for s1, s2 in zip(steps1, steps2, strict=True):
            assert s1.mid_price == s2.mid_price
            assert s1.bid_price == s2.bid_price
            assert s1.ask_price == s2.ask_price
            assert s1.volume == s2.volume

    def test_different_seeds_different_prices(self) -> None:
        """Different seeds produce different price sequences."""
        config1 = MarketTwinConfig(seed="seed-a")
        config2 = MarketTwinConfig(seed="seed-b")
        twin1 = MarketTwin(config1)
        twin2 = MarketTwin(config2)

        steps1 = twin1.generate_steps(10)
        steps2 = twin2.generate_steps(10)

        prices1 = [s.mid_price for s in steps1]
        prices2 = [s.mid_price for s in steps2]
        assert prices1 != prices2

    def test_random_walk_model(self) -> None:
        """Random walk model produces valid price paths."""
        config = MarketTwinConfig(
            seed="rw-test",
            model=MicrostructureModel.RANDOM_WALK,
            volatility="0.01",
        )
        twin = MarketTwin(config)
        steps = twin.generate_steps(100)

        # Prices should stay within a reasonable range of initial
        initial = Decimal(config.initial_price)
        for step in steps:
            price = Decimal(step.mid_price)
            assert price > 0
            # Random walk shouldn't drift more than 90% in 100 steps with 1% vol
            assert price > initial * Decimal("0.1")

    def test_mean_reversion_model(self) -> None:
        """Mean reversion model produces prices that revert to mean."""
        config = MarketTwinConfig(
            seed="mr-test",
            model=MicrostructureModel.MEAN_REVERSION,
            mean_reversion_rate="0.5",
            volatility="0.01",
        )
        twin = MarketTwin(config)
        steps = twin.generate_steps(200)

        # Mean reversion should keep prices closer to the mean
        mean_price = Decimal(config.initial_price)
        max_deviation = Decimal("0.5")  # 50% max deviation
        for step in steps:
            price = Decimal(step.mid_price)
            deviation = abs(price - mean_price) / mean_price
            assert deviation < max_deviation

    def test_ornstein_uhlenbeck_model(self) -> None:
        """Ornstein-Uhlenbeck model produces valid prices."""
        config = MarketTwinConfig(
            seed="ou-test",
            model=MicrostructureModel.ORNSTEIN_UHLENBECK,
            mean_reversion_rate="0.3",
            volatility="0.5",
        )
        twin = MarketTwin(config)
        steps = twin.generate_steps(50)

        for step in steps:
            assert Decimal(step.mid_price) > 0

    def test_volume_weighted_model(self) -> None:
        """Volume-weighted model produces valid prices."""
        config = MarketTwinConfig(
            seed="vw-test",
            model=MicrostructureModel.VOLUME_WEIGHTED,
        )
        twin = MarketTwin(config)
        steps = twin.generate_steps(50)

        for step in steps:
            assert Decimal(step.mid_price) > 0

    def test_get_ticker(self) -> None:
        """get_ticker returns a valid Ticker."""
        config = MarketTwinConfig(seed="ticker-test")
        twin = MarketTwin(config)
        symbol = Symbol.parse("BTC/USDT")
        ticker = twin.get_ticker(symbol)

        assert ticker.symbol.pair == "BTC/USDT"
        assert Decimal(ticker.last_price) > 0
        assert Decimal(ticker.bid) > 0
        assert Decimal(ticker.ask) > 0

    def test_get_order_book(self) -> None:
        """get_order_book returns a valid order book."""
        config = MarketTwinConfig(seed="ob-test")
        twin = MarketTwin(config)
        symbol = Symbol.parse("BTC/USDT")
        book = twin.get_order_book(symbol, depth=5)

        assert len(book.bids) == 5
        assert len(book.asks) == 5
        for bid in book.bids:
            assert Decimal(bid.price) > 0
        for ask in book.asks:
            assert Decimal(ask.price) > 0

    def test_get_candles(self) -> None:
        """get_candles returns valid candles."""
        from contracts.market_data import Timeframe

        config = MarketTwinConfig(seed="candle-test")
        twin = MarketTwin(config)
        symbol = Symbol.parse("BTC/USDT")
        candles = twin.get_candles(symbol, Timeframe.ONE_MINUTE, 10)

        assert len(candles) == 10
        for candle in candles:
            assert Decimal(candle.close) > 0
            assert Decimal(candle.high) >= Decimal(candle.close)
            assert Decimal(candle.low) <= Decimal(candle.close)

    def test_get_trades(self) -> None:
        """get_trades returns valid trades."""
        config = MarketTwinConfig(seed="trade-test")
        twin = MarketTwin(config)
        symbol = Symbol.parse("BTC/USDT")
        trades = twin.get_trades(symbol, 20)

        assert len(trades) == 20
        for trade in trades:
            assert trade.side in ("buy", "sell")
            assert Decimal(trade.price) > 0

    def test_reset(self) -> None:
        """Reset returns the twin to initial state."""
        config = MarketTwinConfig(seed="reset-test")
        twin = MarketTwin(config)
        twin.generate_steps(50)
        assert len(twin.steps) == 50

        twin.reset()
        assert len(twin.steps) == 0
        assert twin.current_price == config.initial_price


# ── Adapter Conformance Suite Tests ──


class TestAdapterConformanceSuite:
    """Test the adapter conformance suite."""

    @pytest.fixture
    def adapter(self) -> ExchangeSimulator:
        """Create a connected ExchangeSimulator for conformance testing."""
        sim = ExchangeSimulator()
        sim.connect()
        return sim

    def test_conformance_suite_all_pass(self, adapter: ExchangeSimulator) -> None:
        """A conformant adapter passes all conformance checks."""
        suite = AdapterConformanceSuite(adapter)
        result = suite.run_all_checks()

        assert result.all_passed is True
        assert result.failed == 0
        assert result.total_checks > 0
        assert result.passed == result.total_checks

    def test_idempotent_submission_check(self, adapter: ExchangeSimulator) -> None:
        """Idempotent submission check passes for a conformant adapter."""
        suite = AdapterConformanceSuite(adapter)
        results = suite.run_all_checks()

        idempotent_results = [
            r for r in results.results if r.check_type.value == "idempotent_submission"
        ]
        assert len(idempotent_results) == 1
        assert idempotent_results[0].status is ConformanceStatus.PASSED

    def test_tenant_isolation_check(self, adapter: ExchangeSimulator) -> None:
        """Tenant isolation check passes for a conformant adapter."""
        suite = AdapterConformanceSuite(adapter)
        results = suite.run_all_checks()

        tenant_results = [r for r in results.results if r.check_type.value == "tenant_isolation"]
        assert len(tenant_results) == 1
        assert tenant_results[0].status is ConformanceStatus.PASSED

    def test_connection_lifecycle_check(self, adapter: ExchangeSimulator) -> None:
        """Connection lifecycle check passes for a conformant adapter."""
        suite = AdapterConformanceSuite(adapter)
        results = suite.run_all_checks()

        conn_results = [r for r in results.results if r.check_type.value == "connection_lifecycle"]
        assert len(conn_results) == 1
        assert conn_results[0].status is ConformanceStatus.PASSED

    def test_cancel_idempotent_check(self, adapter: ExchangeSimulator) -> None:
        """Cancel idempotency check passes for a conformant adapter."""
        suite = AdapterConformanceSuite(adapter)
        results = suite.run_all_checks()

        cancel_results = [
            r for r in results.results if r.check_type.value == "cancel_is_idempotent"
        ]
        assert len(cancel_results) == 1
        assert cancel_results[0].status is ConformanceStatus.PASSED


# ── Snapshot Reconciliation Tests ──


class TestSnapshotReconciliation:
    """Test snapshot reconciliation."""

    def test_matching_snapshots(self) -> None:
        """Matching snapshots reconcile as MATCHED."""
        reconciler = SnapshotReconciler()

        snap1 = reconciler.capture_snapshot(
            seed="snap-test",
            step_index=10,
            ledger_balances={"acc-1": "100.0", "acc-2": "50.0"},
            order_states={"order-1": "filled"},
            exposure="1000.0",
        )
        snap2 = reconciler.capture_snapshot(
            seed="snap-test",
            step_index=10,
            ledger_balances={"acc-1": "100.0", "acc-2": "50.0"},
            order_states={"order-1": "filled"},
            exposure="1000.0",
        )

        result = reconciler.reconcile(snap1, snap2)
        assert result.status is SnapshotStatus.MATCHED
        assert result.is_match is True
        assert len(result.divergences) == 0

    def test_diverging_snapshots(self) -> None:
        """Diverging snapshots reconcile as DISCREPANCY with listed divergences."""
        reconciler = SnapshotReconciler()

        snap1 = reconciler.capture_snapshot(
            seed="snap-diverge",
            step_index=10,
            ledger_balances={"acc-1": "100.0"},
            order_states={"order-1": "filled"},
            exposure="1000.0",
        )
        snap2 = reconciler.capture_snapshot(
            seed="snap-diverge",
            step_index=10,
            ledger_balances={"acc-1": "200.0"},  # Different balance
            order_states={"order-1": "filled"},
            exposure="1000.0",
        )

        result = reconciler.reconcile(snap1, snap2)
        assert result.status is SnapshotStatus.DISCREPANCY
        assert result.is_match is False
        assert len(result.divergences) > 0

    def test_state_hash_is_deterministic(self) -> None:
        """Same state → same hash."""
        reconciler = SnapshotReconciler()

        snap1 = reconciler.capture_snapshot(
            seed="hash-test",
            step_index=5,
            ledger_balances={"acc-1": "100.0"},
            order_states={"o-1": "filled"},
            exposure="100.0",
        )
        snap2 = reconciler.capture_snapshot(
            seed="hash-test",
            step_index=5,
            ledger_balances={"acc-1": "100.0"},
            order_states={"o-1": "filled"},
            exposure="100.0",
        )

        assert snap1.state_hash == snap2.state_hash

    def test_different_state_different_hash(self) -> None:
        """Different state → different hash."""
        reconciler = SnapshotReconciler()

        snap1 = reconciler.capture_snapshot(
            seed="diff-hash",
            step_index=5,
            ledger_balances={"acc-1": "100.0"},
            order_states={"o-1": "filled"},
        )
        snap2 = reconciler.capture_snapshot(
            seed="diff-hash",
            step_index=5,
            ledger_balances={"acc-1": "200.0"},  # Different
            order_states={"o-1": "filled"},
        )

        assert snap1.state_hash != snap2.state_hash


# ── PITR Restore Tests ──


class TestPITRRestore:
    """Test PITR restore with ledger diff."""

    def test_perfect_restore(self) -> None:
        """A perfect restore has zero diffs and is VERIFIED."""
        restorer = PITRRestorer()
        config = PITRConfig(restore_point=datetime.now(UTC))

        original = {
            "acc-1": {"BTC": "1.5", "USDT": "50000.0"},
            "acc-2": {"BTC": "0.5", "USDT": "25000.0"},
        }
        restored = dict(original)  # identical

        result = restorer.restore(config, original, restored)

        assert result.status is PITRStatus.VERIFIED
        assert result.verified is True
        assert result.total_diff_count == 0
        assert Decimal(result.max_abs_delta) == 0

    def test_imperfect_restore(self) -> None:
        """An imperfect restore has diffs and is DIFF_DETECTED."""
        restorer = PITRRestorer()
        config = PITRConfig(restore_point=datetime.now(UTC))

        original = {
            "acc-1": {"BTC": "1.5", "USDT": "50000.0"},
        }
        restored = {
            "acc-1": {"BTC": "1.3", "USDT": "50000.0"},  # BTC balance differs
        }

        result = restorer.restore(config, original, restored)

        assert result.status is PITRStatus.DIFF_DETECTED
        assert result.verified is False
        assert result.total_diff_count > 0
        assert Decimal(result.max_abs_delta) > 0

    def test_missing_account_in_restore(self) -> None:
        """A missing account in the restore is detected as a diff."""
        restorer = PITRRestorer()
        config = PITRConfig(restore_point=datetime.now(UTC))

        original = {
            "acc-1": {"BTC": "1.0"},
            "acc-2": {"BTC": "2.0"},
        }
        restored = {
            "acc-1": {"BTC": "1.0"},
            # acc-2 missing
        }

        result = restorer.restore(config, original, restored)

        assert result.total_diff_count > 0
        assert result.verified is False

    def test_ledger_diff_entry_delta(self) -> None:
        """LedgerDiffEntry.delta computes correctly."""
        from contracts.simulation import LedgerDiffEntry

        entry = LedgerDiffEntry(
            account_id="acc-1",
            asset="BTC",
            original_balance="100.0",
            restored_balance="80.0",
        )
        assert Decimal(entry.delta) == Decimal("-20.0")
        assert entry.has_diff is True

        entry2 = LedgerDiffEntry(
            account_id="acc-2",
            asset="USDT",
            original_balance="50.0",
            restored_balance="50.0",
        )
        assert Decimal(entry2.delta) == Decimal("0")
        assert entry2.has_diff is False


# ── Load and Chaos Drill Tests ──


class TestLoadDrillRunner:
    """Test the load drill runner."""

    def test_load_drill_passes(self) -> None:
        """A load drill with 0% error rate passes."""
        runner = LoadDrillRunner()
        config = LoadDrillConfig(
            virtual_users=10,
            duration_seconds=30,
            requests_per_second="50.0",
        )

        result = runner.run_load_drill(config)

        assert result.status is DrillStatus.PASSED
        assert result.total_requests > 0
        assert Decimal(result.error_rate_pct) == Decimal("0")
        assert result.completed_at is not None

    def test_load_drill_records_metrics(self) -> None:
        """Load drill records throughput and latency metrics."""
        runner = LoadDrillRunner()
        config = LoadDrillConfig(
            virtual_users=20,
            duration_seconds=60,
            requests_per_second="100.0",
        )

        result = runner.run_load_drill(config)

        assert result.total_requests == 6000  # 100 rps * 60s
        assert Decimal(result.avg_latency_ms) > 0
        assert Decimal(result.p99_latency_ms) > 0


class TestChaosDrillRunner:
    """Test the chaos drill runner."""

    def test_chaos_drill_passes(self) -> None:
        """A chaos drill in simulation passes."""
        runner = ChaosDrillRunner()
        config = ChaosDrillConfig(
            fault_type=DrillType.NETWORK_PARTITION,
            blast_radius_pct="50.0",
            duration_seconds=30,
        )

        result = runner.run_chaos_drill(config)

        assert result.status is DrillStatus.PASSED
        assert result.drill_type is DrillType.NETWORK_PARTITION
        assert result.completed_at is not None

    def test_chaos_drill_pod_kill(self) -> None:
        """Pod kill drill type is recorded."""
        runner = ChaosDrillRunner()
        config = ChaosDrillConfig(
            fault_type=DrillType.POD_KILL,
            blast_radius_pct="25.0",
            duration_seconds=10,
        )

        result = runner.run_chaos_drill(config)

        assert result.drill_type is DrillType.POD_KILL
        assert "pod_kill" in result.notes


# ── Reality Gap Tracker Tests ──


class TestRealityGapTracker:
    """Test the reality gap tracker."""

    def test_record_metric(self) -> None:
        """Recording a metric computes the gap."""
        tracker = RealityGapTracker()
        metric = tracker.record_metric("price_accuracy", "50000.0", "51000.0")

        assert Decimal(metric.gap) == Decimal("1000.0")
        assert metric.metric_name == "price_accuracy"

    def test_generate_report(self) -> None:
        """Generating a report aggregates all metrics."""
        tracker = RealityGapTracker()
        tracker.record_metric("metric-1", "100.0", "105.0")
        tracker.record_metric("metric-2", "200.0", "190.0")

        report = tracker.generate_report("test-seed")

        assert len(report.metrics) == 2
        assert Decimal(report.total_gap) == Decimal("15.0")  # |5| + |10|

    def test_zero_gap(self) -> None:
        """Matching values produce zero gap."""
        tracker = RealityGapTracker()
        tracker.record_metric("perfect", "100.0", "100.0")

        report = tracker.generate_report("zero-gap")
        assert Decimal(report.total_gap) == Decimal("0")

    def test_reality_gap_is_not_accuracy_claim(self) -> None:
        """Reality gap metrics are explicitly deltas, not accuracy claims."""
        tracker = RealityGapTracker()
        metric = tracker.record_metric(
            "fill_rate",
            "0.85",
            "0.90",
            notes="simulated vs historical reference — NOT a claim of real-world accuracy",
        )

        assert "NOT" in metric.notes
        assert Decimal(metric.gap) == Decimal("0.05")


# ── E5 Acceptance Criteria Tests ──


class TestE5Acceptance:
    """Test E5 acceptance criteria directly."""

    def test_same_seed_produces_identical_results(self) -> None:
        """E5 acceptance: same seed produces identical results."""
        engine = DSTEngine()
        seed = SimulationSeed(seed="acceptance-determinism")
        config = SimulationRunConfig(seeds=[seed], num_orders=100)

        r1 = engine.run_single_seed(config, seed)
        r2 = engine.run_single_seed(config, seed)
        r3 = engine.run_single_seed(config, seed)

        assert r1.output_hash == r2.output_hash == r3.output_hash

    def test_reality_gap_tracked(self) -> None:
        """E5 acceptance: reality gap tracked."""
        tracker = RealityGapTracker()
        tracker.record_metric("price_path", "50000", "49500")
        tracker.record_metric("volatility", "0.02", "0.025")

        report = tracker.generate_report("acceptance-gap")

        assert len(report.metrics) == 2
        assert Decimal(report.total_gap) > 0

    def test_performance_evidence_recorded(self) -> None:
        """E5 acceptance: performance evidence recorded."""
        load_runner = LoadDrillRunner()
        chaos_runner = ChaosDrillRunner()

        load_result = load_runner.run_load_drill(LoadDrillConfig())
        chaos_result = chaos_runner.run_chaos_drill(ChaosDrillConfig())

        assert load_result.status in (DrillStatus.PASSED, DrillStatus.FAILED)
        assert chaos_result.status in (DrillStatus.PASSED, DrillStatus.FAILED)
        assert load_result.completed_at is not None
        assert chaos_result.completed_at is not None

    def test_multi_seed_determinism_verified(self) -> None:
        """E5 acceptance: multi-seed runs verify determinism."""
        engine = DSTEngine()
        seeds = [SimulationSeed(seed=f"nightly-{i}") for i in range(10)]
        config = SimulationRunConfig(seeds=seeds, num_orders=20)

        result = engine.run_multi_seed(config)

        assert result.determinism_verified is True
        assert result.all_completed is True
        assert len(result.run_results) == 10

    def test_pitr_restore_with_ledger_diff(self) -> None:
        """E5 acceptance: PITR restore with ledger diff."""
        restorer = PITRRestorer()
        config = PITRConfig(restore_point=datetime.now(UTC))

        original = {"acc-1": {"BTC": "1.0", "USDT": "50000.0"}}
        restored = {"acc-1": {"BTC": "1.0", "USDT": "50000.0"}}

        result = restorer.restore(config, original, restored)

        assert result.verified is True
        assert result.total_diff_count == 0
        assert len(result.ledger_diffs) == 2  # BTC + USDT

    def test_adapter_conformance_all_pass(self) -> None:
        """E5 acceptance: adapter conformance suite passes for conformant adapter."""
        sim = ExchangeSimulator()
        sim.connect()
        suite = AdapterConformanceSuite(sim)

        result = suite.run_all_checks()

        assert result.all_passed is True
        assert result.failed == 0
