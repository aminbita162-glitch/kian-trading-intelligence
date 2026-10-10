"""Tests for mining contracts — Phase 07 deliverables 1-10.

Per Section 09 (Mining Operations):
- 09.1: Mining simulation — hash rate, network difficulty, expected rewards,
  pool fees, electricity costs, equipment efficiency, hardware depreciation,
  temperature, downtime, net profitability, uncertainty.
- 09.2: Hardware and pool integration — requires approved adapter, verified
  operator authority, safety limits, reliable telemetry, failure handling,
  explicit authorization.

Per AD-015: begin with simulation and profitability validation. Real hardware
and pool integration require explicit approval and safety controls.

Per AD-023: deterministic simulation, mining simulation, and repeatable
verification before live operations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from contracts.mining import (
    BlockReward,
    DepreciationConfig,
    ElectricityConfig,
    EquipmentSpec,
    FailureEvent,
    FailureEventId,
    FailureType,
    HashRate,
    HashRateUnit,
    MiningEquipmentId,
    MiningFinancialEntry,
    MiningHardwareStatus,
    MiningOperationStatus,
    MiningSafetyLimits,
    MiningSafetyState,
    MiningSessionConfig,
    MiningSessionId,
    MiningSimulationResult,
    NetworkDifficulty,
    PoolAdapterId,
    PoolConfig,
    PoolPayoutScheme,
    SimulatedPoolAdapter,
    TelemetryHistory,
    TelemetryId,
    TelemetryReading,
    TemperatureAction,
    TemperaturePolicy,
)
from services.mining import MiningSimulator

# ── Test fixtures ──


@pytest.fixture
def equipment() -> EquipmentSpec:
    return EquipmentSpec.create(
        name="Test Miner X1",
        hash_rate_value="100",
        hash_rate_unit=HashRateUnit.TERAHASH_PER_S,
        power_consumption_w="3000",
        cost="5000",
        useful_life_months=36,
        salvage_value="500",
        min_operating_temp_c="0",
        max_operating_temp_c="80",
        throttle_temp_c="70",
        shutdown_temp_c="85",
    )


@pytest.fixture
def pool() -> PoolConfig:
    return PoolConfig.create(
        name="TestPool",
        url="stratum+tcp://simulation.example.com:3333",
        fee_pct="1.5",
        payout_scheme=PoolPayoutScheme.PPS,
        min_payout="0.001",
    )


@pytest.fixture
def electricity() -> ElectricityConfig:
    return ElectricityConfig.from_str("0.12", "USD")


@pytest.fixture
def network_difficulty() -> NetworkDifficulty:
    return NetworkDifficulty.from_str("50000000000")


@pytest.fixture
def block_reward() -> BlockReward:
    return BlockReward.from_str("6.25")


@pytest.fixture
def mining_session_config(
    equipment: EquipmentSpec,
    pool: PoolConfig,
    electricity: ElectricityConfig,
    network_difficulty: NetworkDifficulty,
    block_reward: BlockReward,
) -> MiningSessionConfig:
    return MiningSessionConfig.create(
        equipment=equipment,
        pool=pool,
        electricity=electricity,
        network_difficulty=network_difficulty,
        block_reward=block_reward,
        btc_price="50000",
        uptime_pct="95",
    )


# ── Deliverable 1: Mining Simulator ──


class TestMiningSimulator:
    """Tests for the mining simulator service."""

    def test_simulation_runs_and_returns_result(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        result = sim.run_simulation(mining_session_config)
        assert result is not None
        assert isinstance(result, MiningSimulationResult)
        assert result.is_simulation is True
        assert result.session_id == mining_session_config.session_id

    def test_simulation_is_deterministic(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:
        """Per AD-023: same inputs produce same outputs."""

        sim1 = MiningSimulator()
        sim2 = MiningSimulator()
        result1 = sim1.run_simulation(mining_session_config)
        result2 = sim2.run_simulation(mining_session_config)
        assert result1.daily_gross_revenue_btc == result2.daily_gross_revenue_btc
        assert result1.daily_net_revenue_btc == result2.daily_net_revenue_btc
        assert result1.daily_electricity_cost == result2.daily_electricity_cost
        assert result1.daily_net_profit == result2.daily_net_profit
        assert result1.break_even_btc_price == result2.break_even_btc_price

    def test_simulation_is_simulation_only(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:
        """Per AD-015: simulation only, not real hardware."""

        sim = MiningSimulator()
        result = sim.run_simulation(mining_session_config)
        assert result.is_simulation is True
        assert sim.is_simulation is True

    def test_simulation_calculates_gross_revenue(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        result = sim.run_simulation(mining_session_config)
        assert result.daily_gross_revenue_btc > 0

    def test_simulation_calculates_net_revenue_after_pool_fee(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        result = sim.run_simulation(mining_session_config)
        assert result.daily_net_revenue_btc < result.daily_gross_revenue_btc
        assert result.daily_pool_fee_btc > 0
        assert (
            result.daily_net_revenue_btc
            == result.daily_gross_revenue_btc - result.daily_pool_fee_btc
        )

    def test_simulation_calculates_net_profit(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        result = sim.run_simulation(mining_session_config)
        # net_profit = revenue_fiat - electricity_cost - depreciation
        expected_revenue_fiat = result.daily_net_revenue_btc * Decimal("50000")
        expected_net = (
            expected_revenue_fiat - result.daily_electricity_cost - result.daily_depreciation
        )
        assert result.daily_net_profit == expected_net

    def test_simulation_calculates_uncertainty_range(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        result = sim.run_simulation(mining_session_config)
        low, high = result.uncertainty_range
        assert low < result.daily_net_profit
        assert high > result.daily_net_profit
        # ±15% range: verify each bound independently to avoid
        # Decimal subtraction precision loss.
        expected_low = result.daily_net_profit * Decimal("0.85")
        expected_high = result.daily_net_profit * Decimal("1.15")
        assert low == expected_low
        assert high == expected_high

    def test_simulation_result_get_by_session_id(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        sim.run_simulation(mining_session_config)
        result = sim.get_result(mining_session_config.session_id)
        assert result is not None
        assert result.session_id == mining_session_config.session_id

    def test_simulation_result_none_for_unknown_session(self) -> None:

        sim = MiningSimulator()
        result = sim.get_result(MiningSessionId.generate())
        assert result is None

    def test_emergency_stop_blocks_simulation(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:
        """Per AD-013: emergency stop must block new operations."""

        sim = MiningSimulator()
        sim.trigger_emergency_stop()
        with pytest.raises(PermissionError, match="emergency stop"):
            sim.run_simulation(mining_session_config)

    def test_clear_emergency_stop_allows_simulation(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        sim.trigger_emergency_stop()
        sim.clear_emergency_stop("owner")
        result = sim.run_simulation(mining_session_config)
        assert result is not None

    def test_clear_emergency_stop_requires_authorized_by(self) -> None:

        sim = MiningSimulator()
        sim.trigger_emergency_stop()
        with pytest.raises(ValueError, match="authorized_by"):
            sim.clear_emergency_stop("")

    def test_reset_clears_all_state(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        sim.run_simulation(mining_session_config)
        assert sim.session_count == 1
        sim.reset()
        assert sim.session_count == 0


# ── Deliverable 2: Hash Rate and Reward Models ──


class TestHashRateModel:
    """Tests for hash rate and reward models."""

    def test_hash_rate_creation(self) -> None:
        hr = HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S)
        assert hr.value == Decimal("100")
        assert hr.unit == HashRateUnit.TERAHASH_PER_S

    def test_hash_rate_from_str(self) -> None:
        hr = HashRate.from_str("150.5", HashRateUnit.GIGAHASH_PER_S)
        assert hr.value == Decimal("150.5")
        assert hr.unit == HashRateUnit.GIGAHASH_PER_S

    def test_hash_rate_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            HashRate(Decimal("-1"), HashRateUnit.TERAHASH_PER_S)

    def test_hash_rate_conversion_to_hps(self) -> None:
        hr = HashRate(Decimal("1"), HashRateUnit.TERAHASH_PER_S)
        expected = Decimal("1000000000000")
        assert hr.hash_per_second == expected

    def test_hash_rate_conversion_ghps(self) -> None:
        hr = HashRate(Decimal("1"), HashRateUnit.GIGAHASH_PER_S)
        expected = Decimal("1000000000")
        assert hr.hash_per_second == expected

    def test_hash_rate_conversion_mhps(self) -> None:
        hr = HashRate(Decimal("1"), HashRateUnit.MEGAHASH_PER_S)
        expected = Decimal("1000000")
        assert hr.hash_per_second == expected

    def test_hash_rate_conversion_khps(self) -> None:
        hr = HashRate(Decimal("1"), HashRateUnit.KILOHASH_PER_S)
        expected = Decimal("1000")
        assert hr.hash_per_second == expected

    def test_hash_rate_conversion_hps(self) -> None:
        hr = HashRate(Decimal("1"), HashRateUnit.HASH_PER_S)
        assert hr.hash_per_second == Decimal("1")

    def test_hash_rate_conversion_peta(self) -> None:
        hr = HashRate(Decimal("1"), HashRateUnit.PETAHASH_PER_S)
        expected = Decimal("1000000000000000")
        assert hr.hash_per_second == expected

    def test_hash_rate_to_unit_conversion(self) -> None:
        hr = HashRate(Decimal("1"), HashRateUnit.TERAHASH_PER_S)
        converted = hr.to_unit(HashRateUnit.GIGAHASH_PER_S)
        assert converted.value == Decimal("1000")
        assert converted.unit == HashRateUnit.GIGAHASH_PER_S

    def test_hash_rate_str_representation(self) -> None:
        hr = HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S)
        assert str(hr) == "100 TH/s"


class TestNetworkDifficulty:
    """Tests for network difficulty model."""

    def test_difficulty_creation(self) -> None:
        d = NetworkDifficulty(Decimal("50000000000"))
        assert d.value == Decimal("50000000000")

    def test_difficulty_from_str(self) -> None:
        d = NetworkDifficulty.from_str("100000000000")
        assert d.value == Decimal("100000000000")

    def test_difficulty_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            NetworkDifficulty(Decimal("0"))

    def test_difficulty_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            NetworkDifficulty(Decimal("-1"))


class TestBlockReward:
    """Tests for block reward model."""

    def test_reward_creation(self) -> None:
        r = BlockReward(Decimal("6.25"))
        assert r.reward_btc == Decimal("6.25")

    def test_reward_from_str(self) -> None:
        r = BlockReward.from_str("3.125")
        assert r.reward_btc == Decimal("3.125")

    def test_reward_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            BlockReward(Decimal("0"))

    def test_reward_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            BlockReward(Decimal("-1"))


class TestEquipmentSpec:
    """Tests for equipment specification."""

    def test_equipment_creation(self, equipment: EquipmentSpec) -> None:
        assert equipment.name == "Test Miner X1"
        assert equipment.power_consumption_w == Decimal("3000")
        assert equipment.cost == Decimal("5000")
        assert equipment.useful_life_months == 36

    def test_equipment_id_is_unique(self) -> None:
        e1 = EquipmentSpec.create(
            name="A",
            hash_rate_value="1",
            hash_rate_unit=HashRateUnit.TERAHASH_PER_S,
            power_consumption_w="100",
            cost="100",
            useful_life_months=12,
        )
        e2 = EquipmentSpec.create(
            name="B",
            hash_rate_value="1",
            hash_rate_unit=HashRateUnit.TERAHASH_PER_S,
            power_consumption_w="100",
            cost="100",
            useful_life_months=12,
        )
        assert e1.equipment_id != e2.equipment_id

    def test_equipment_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name"):
            EquipmentSpec(
                equipment_id=MiningEquipmentId.generate(),
                name="",
                hash_rate=HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S),
                power_consumption_w=Decimal("3000"),
                cost=Decimal("5000"),
                useful_life_months=36,
            )

    def test_equipment_zero_power_raises(self) -> None:
        with pytest.raises(ValueError, match="Power"):
            EquipmentSpec(
                equipment_id=MiningEquipmentId.generate(),
                name="Test",
                hash_rate=HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S),
                power_consumption_w=Decimal("0"),
                cost=Decimal("5000"),
                useful_life_months=36,
            )

    def test_equipment_negative_cost_raises(self) -> None:
        with pytest.raises(ValueError, match="Cost"):
            EquipmentSpec(
                equipment_id=MiningEquipmentId.generate(),
                name="Test",
                hash_rate=HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S),
                power_consumption_w=Decimal("3000"),
                cost=Decimal("-1"),
                useful_life_months=36,
            )

    def test_equipment_zero_useful_life_raises(self) -> None:
        with pytest.raises(ValueError, match="Useful life"):
            EquipmentSpec(
                equipment_id=MiningEquipmentId.generate(),
                name="Test",
                hash_rate=HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S),
                power_consumption_w=Decimal("3000"),
                cost=Decimal("5000"),
                useful_life_months=0,
            )

    def test_equipment_salvage_exceeding_cost_raises(self) -> None:
        with pytest.raises(ValueError, match="Salvage"):
            EquipmentSpec(
                equipment_id=MiningEquipmentId.generate(),
                name="Test",
                hash_rate=HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S),
                power_consumption_w=Decimal("3000"),
                cost=Decimal("5000"),
                useful_life_months=36,
                salvage_value=Decimal("6000"),
            )

    def test_equipment_efficiency_j_per_th(self, equipment: EquipmentSpec) -> None:
        eff = equipment.efficiency_j_per_th
        assert eff > 0
        # 3000W / 100 TH/s = 30 J/TH
        assert eff == Decimal("30")

    def test_equipment_temp_bounds_validated(self) -> None:
        with pytest.raises(ValueError, match="Min operating"):
            EquipmentSpec(
                equipment_id=MiningEquipmentId.generate(),
                name="Test",
                hash_rate=HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S),
                power_consumption_w=Decimal("3000"),
                cost=Decimal("5000"),
                useful_life_months=36,
                min_operating_temp_c=Decimal("90"),
                max_operating_temp_c=Decimal("80"),
            )

    def test_equipment_throttle_exceeds_shutdown_raises(self) -> None:
        with pytest.raises(ValueError, match="Throttle"):
            EquipmentSpec(
                equipment_id=MiningEquipmentId.generate(),
                name="Test",
                hash_rate=HashRate(Decimal("100"), HashRateUnit.TERAHASH_PER_S),
                power_consumption_w=Decimal("3000"),
                cost=Decimal("5000"),
                useful_life_months=36,
                throttle_temp_c=Decimal("95"),
                shutdown_temp_c=Decimal("90"),
            )


# ── Deliverable 3: Electricity Cost ──


class TestElectricityCost:
    """Tests for electricity cost model."""

    def test_electricity_creation(self) -> None:
        ec = ElectricityConfig(Decimal("0.12"), "USD")
        assert ec.rate_per_kwh == Decimal("0.12")
        assert ec.currency == "USD"

    def test_electricity_from_str(self) -> None:
        ec = ElectricityConfig.from_str("0.15", "EUR")
        assert ec.rate_per_kwh == Decimal("0.15")
        assert ec.currency == "EUR"

    def test_electricity_default_currency(self) -> None:
        ec = ElectricityConfig.from_str("0.10")
        assert ec.currency == "USD"

    def test_electricity_negative_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="rate"):
            ElectricityConfig(Decimal("-0.01"), "USD")

    def test_electricity_empty_currency_raises(self) -> None:
        with pytest.raises(ValueError, match="Currency"):
            ElectricityConfig(Decimal("0.12"), "")

    def test_daily_cost(self) -> None:
        ec = ElectricityConfig(Decimal("0.12"), "USD")
        # 3000W = 3kW, 24h * 95% uptime = 22.8h, 3 * 22.8 * 0.12 = 8.208
        cost = ec.daily_cost(Decimal("3000"), Decimal("95"))
        expected = Decimal("3") * Decimal("22.8") * Decimal("0.12")
        assert cost == expected

    def test_daily_cost_zero_power(self) -> None:
        ec = ElectricityConfig(Decimal("0.12"), "USD")
        cost = ec.daily_cost(Decimal("0"), Decimal("95"))
        assert cost == Decimal("0")

    def test_daily_cost_full_uptime(self) -> None:
        ec = ElectricityConfig(Decimal("0.10"), "USD")
        # 1000W = 1kW, 24h * 100% = 24h, 1 * 24 * 0.10 = 2.40
        cost = ec.daily_cost(Decimal("1000"), Decimal("100"))
        assert cost == Decimal("2.40")

    def test_daily_cost_zero_uptime(self) -> None:
        ec = ElectricityConfig(Decimal("0.12"), "USD")
        cost = ec.daily_cost(Decimal("3000"), Decimal("0"))
        assert cost == Decimal("0")

    def test_daily_cost_invalid_uptime_raises(self) -> None:
        ec = ElectricityConfig(Decimal("0.12"), "USD")
        with pytest.raises(ValueError, match="Uptime"):
            ec.daily_cost(Decimal("3000"), Decimal("150"))

    def test_daily_cost_negative_power_raises(self) -> None:
        ec = ElectricityConfig(Decimal("0.12"), "USD")
        with pytest.raises(ValueError, match="Power"):
            ec.daily_cost(Decimal("-1"), Decimal("95"))

    def test_monthly_cost(self) -> None:
        ec = ElectricityConfig(Decimal("0.12"), "USD")
        daily = ec.daily_cost(Decimal("3000"), Decimal("95"))
        monthly = ec.monthly_cost(Decimal("3000"), Decimal("95"))
        assert monthly == daily * Decimal("30")


# ── Deliverable 4: Depreciation ──


class TestDepreciation:
    """Tests for depreciation model."""

    def test_depreciation_creation(self) -> None:
        dep = DepreciationConfig(
            initial_cost=Decimal("5000"),
            salvage_value=Decimal("500"),
            useful_life_months=36,
        )
        assert dep.initial_cost == Decimal("5000")
        assert dep.salvage_value == Decimal("500")
        assert dep.useful_life_months == 36

    def test_depreciation_from_equipment(self, equipment: EquipmentSpec) -> None:
        dep = DepreciationConfig.from_equipment(equipment)
        assert dep.initial_cost == Decimal("5000")
        assert dep.salvage_value == Decimal("500")
        assert dep.useful_life_months == 36

    def test_monthly_depreciation(self) -> None:
        dep = DepreciationConfig(
            initial_cost=Decimal("5000"),
            salvage_value=Decimal("500"),
            useful_life_months=36,
        )
        # (5000 - 500) / 36 = 125
        assert dep.monthly_depreciation == Decimal("125")

    def test_daily_depreciation(self) -> None:
        dep = DepreciationConfig(
            initial_cost=Decimal("5000"),
            salvage_value=Decimal("500"),
            useful_life_months=36,
        )
        # 125 / 30 = 4.1666...
        daily = dep.daily_depreciation
        expected = Decimal("125") / Decimal("30")
        assert daily == expected

    def test_depreciation_zero_salvage(self) -> None:
        dep = DepreciationConfig(
            initial_cost=Decimal("3600"),
            salvage_value=Decimal("0"),
            useful_life_months=36,
        )
        assert dep.monthly_depreciation == Decimal("100")

    def test_depreciation_negative_cost_raises(self) -> None:
        with pytest.raises(ValueError, match="Initial cost"):
            DepreciationConfig(
                initial_cost=Decimal("-1"),
                salvage_value=Decimal("0"),
                useful_life_months=36,
            )

    def test_depreciation_salvage_exceeds_cost_raises(self) -> None:
        with pytest.raises(ValueError, match="Salvage"):
            DepreciationConfig(
                initial_cost=Decimal("100"),
                salvage_value=Decimal("200"),
                useful_life_months=36,
            )

    def test_depreciation_zero_life_raises(self) -> None:
        with pytest.raises(ValueError, match="Useful life"):
            DepreciationConfig(
                initial_cost=Decimal("5000"),
                salvage_value=Decimal("0"),
                useful_life_months=0,
            )


# ── Deliverable 5: Pool Interfaces ──


class TestPoolConfig:
    """Tests for pool configuration."""

    def test_pool_creation(self, pool: PoolConfig) -> None:
        assert pool.name == "TestPool"
        assert pool.fee_pct == Decimal("1.5")
        assert pool.payout_scheme == PoolPayoutScheme.PPS

    def test_pool_fee_fraction(self, pool: PoolConfig) -> None:
        assert pool.fee_fraction == Decimal("0.015")

    def test_pool_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Pool name"):
            PoolConfig(
                pool_id=PoolAdapterId.generate(),
                name="",
                url="stratum+tcp://test:3333",
                fee_pct=Decimal("1"),
            )

    def test_pool_empty_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Pool URL"):
            PoolConfig(
                pool_id=PoolAdapterId.generate(),
                name="Test",
                url="",
                fee_pct=Decimal("1"),
            )

    def test_pool_fee_over_100_raises(self) -> None:
        with pytest.raises(ValueError, match="Pool fee"):
            PoolConfig(
                pool_id=PoolAdapterId.generate(),
                name="Test",
                url="stratum+tcp://test:3333",
                fee_pct=Decimal("101"),
            )

    def test_pool_negative_fee_raises(self) -> None:
        with pytest.raises(ValueError, match="Pool fee"):
            PoolConfig(
                pool_id=PoolAdapterId.generate(),
                name="Test",
                url="stratum+tcp://test:3333",
                fee_pct=Decimal("-1"),
            )

    def test_pool_zero_min_payout_raises(self) -> None:
        with pytest.raises(ValueError, match="Minimum payout"):
            PoolConfig(
                pool_id=PoolAdapterId.generate(),
                name="Test",
                url="stratum+tcp://test:3333",
                fee_pct=Decimal("1"),
                min_payout=Decimal("0"),
            )

    def test_pool_payout_schemes(self) -> None:
        for scheme in PoolPayoutScheme:
            pool = PoolConfig.create(
                name="Test",
                url="stratum+tcp://test:3333",
                fee_pct="1",
                payout_scheme=scheme,
            )
            assert pool.payout_scheme == scheme


class TestSimulatedPoolAdapter:
    """Tests for the simulated pool adapter."""

    def test_pool_adapter_creation(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        assert adapter.pool_config == pool
        assert adapter.is_authorized is False
        assert adapter.is_simulation is True

    def test_pool_adapter_authorize(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        adapter.authorize("operator_1")
        assert adapter.is_authorized is True

    def test_pool_adapter_authorize_empty_raises(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        with pytest.raises(ValueError, match="authorized_by"):
            adapter.authorize("")

    def test_pool_adapter_submit_share(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        adapter.authorize("operator_1")
        result = adapter.submit_share("abc123", MiningEquipmentId.generate())
        assert result is True
        assert adapter.share_count == 1

    def test_pool_adapter_submit_empty_share_raises(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        with pytest.raises(ValueError, match="share_hash"):
            adapter.submit_share("", MiningEquipmentId.generate())

    def test_pool_adapter_add_rewards(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        adapter.add_rewards(Decimal("0.01"))
        # net = 0.01 * (1 - 0.015) = 0.00985
        assert adapter.get_pending_rewards() == Decimal("0.00985")

    def test_pool_adapter_add_negative_rewards_raises(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        with pytest.raises(ValueError, match="non-negative"):
            adapter.add_rewards(Decimal("-0.01"))

    def test_pool_adapter_payout_below_min(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        adapter.add_rewards(Decimal("0.0001"))
        # Below min_payout of 0.001
        assert adapter.request_payout() is False
        assert adapter.get_pending_rewards() == Decimal("0.0000985")

    def test_pool_adapter_payout_above_min(self, pool: PoolConfig) -> None:
        adapter = SimulatedPoolAdapter(pool)
        adapter.add_rewards(Decimal("1"))
        assert adapter.request_payout() is True
        assert adapter.get_pending_rewards() == Decimal("0")
        assert adapter.total_paid > Decimal("0")


# ── Deliverable 6: Hardware Telemetry Contracts ──


class TestTelemetry:
    """Tests for hardware telemetry contracts."""

    def test_telemetry_reading_creation(self, equipment: EquipmentSpec) -> None:
        reading = TelemetryReading(
            reading_id=TelemetryId.generate(),
            equipment_id=equipment.equipment_id,
            timestamp=datetime.now(UTC),
            temperature_c=Decimal("65"),
            hash_rate=equipment.hash_rate,
            power_w=Decimal("3000"),
            fan_speed_rpm=Decimal("2500"),
        )
        assert reading.temperature_c == Decimal("65")
        assert reading.status == MiningHardwareStatus.RUNNING

    def test_telemetry_reading_naive_timestamp_raises(self, equipment: EquipmentSpec) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            TelemetryReading(
                reading_id=TelemetryId.generate(),
                equipment_id=equipment.equipment_id,
                timestamp=datetime.now(),
                temperature_c=Decimal("65"),
                hash_rate=equipment.hash_rate,
                power_w=Decimal("3000"),
            )

    def test_telemetry_history(self, equipment: EquipmentSpec) -> None:
        history = TelemetryHistory(equipment_id=equipment.equipment_id)
        for i in range(5):
            reading = TelemetryReading(
                reading_id=TelemetryId.generate(),
                equipment_id=equipment.equipment_id,
                timestamp=datetime.now(UTC),
                temperature_c=Decimal(60 + i),
                hash_rate=equipment.hash_rate,
                power_w=Decimal("3000"),
            )
            history.add(reading)
        assert history.count == 5
        assert history.latest is not None
        assert history.latest.temperature_c == Decimal("64")
        assert history.avg_temperature == Decimal("62")
        assert history.max_temperature == Decimal("64")

    def test_telemetry_history_wrong_equipment_raises(self, equipment: EquipmentSpec) -> None:
        history = TelemetryHistory(equipment_id=equipment.equipment_id)
        other = MiningEquipmentId.generate()
        with pytest.raises(ValueError, match="equipment_id mismatch"):
            history.add(
                TelemetryReading(
                    reading_id=TelemetryId.generate(),
                    equipment_id=other,
                    timestamp=datetime.now(UTC),
                    temperature_c=Decimal("65"),
                    hash_rate=equipment.hash_rate,
                    power_w=Decimal("3000"),
                )
            )

    def test_telemetry_history_empty(self, equipment: EquipmentSpec) -> None:
        history = TelemetryHistory(equipment_id=equipment.equipment_id)
        assert history.latest is None
        assert history.avg_temperature == Decimal(0)
        assert history.max_temperature == Decimal(0)

    def test_telemetry_avg_hash_rate(self, equipment: EquipmentSpec) -> None:
        history = TelemetryHistory(equipment_id=equipment.equipment_id)
        for _ in range(3):
            history.add(
                TelemetryReading(
                    reading_id=TelemetryId.generate(),
                    equipment_id=equipment.equipment_id,
                    timestamp=datetime.now(UTC),
                    temperature_c=Decimal("60"),
                    hash_rate=equipment.hash_rate,
                    power_w=Decimal("3000"),
                )
            )
        assert history.avg_hash_rate == equipment.hash_rate.hash_per_second

    def test_simulator_generates_telemetry(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        reading = sim.generate_telemetry(
            mining_session_config.session_id,
            mining_session_config,
            elapsed_hours=Decimal("1"),
        )
        assert reading is not None
        assert reading.temperature_c > 0
        assert reading.fan_speed_rpm > 0

    def test_simulator_telemetry_history_stored(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        sim.generate_telemetry(
            mining_session_config.session_id,
            mining_session_config,
        )
        sim.generate_telemetry(
            mining_session_config.session_id,
            mining_session_config,
        )
        history = sim.get_telemetry_history(mining_session_config.session_id)
        assert history is not None
        assert history.count == 2


# ── Deliverable 7: Temperature Policies ──


class TestTemperaturePolicy:
    """Tests for temperature safety policies."""

    def test_policy_default_values(self) -> None:
        policy = TemperaturePolicy()
        assert policy.min_safe == Decimal("0")
        assert policy.max_safe == Decimal("80")
        assert policy.throttle_threshold == Decimal("75")
        assert policy.shutdown_threshold == Decimal("90")
        assert policy.alert_threshold == Decimal("70")

    def test_policy_evaluate_safe(self) -> None:
        policy = TemperaturePolicy()
        assert policy.evaluate(Decimal("50")) is TemperatureAction.NONE

    def test_policy_evaluate_alert(self) -> None:
        policy = TemperaturePolicy()
        assert policy.evaluate(Decimal("70")) is TemperatureAction.ALERT

    def test_policy_evaluate_throttle(self) -> None:
        policy = TemperaturePolicy()
        assert policy.evaluate(Decimal("75")) is TemperatureAction.THROTTLE

    def test_policy_evaluate_shutdown(self) -> None:
        policy = TemperaturePolicy()
        assert policy.evaluate(Decimal("90")) is TemperatureAction.SHUTDOWN

    def test_policy_evaluate_below_min_safe(self) -> None:
        policy = TemperaturePolicy(min_safe=Decimal("10"))
        assert policy.evaluate(Decimal("5")) is TemperatureAction.ALERT

    def test_policy_is_safe(self) -> None:
        policy = TemperaturePolicy()
        assert policy.is_safe(Decimal("50")) is True
        assert policy.is_safe(Decimal("85")) is False
        assert policy.is_safe(Decimal("-1")) is False

    def test_policy_is_violation(self) -> None:
        policy = TemperaturePolicy()
        assert policy.is_violation(Decimal("85")) is True
        assert policy.is_violation(Decimal("50")) is False

    def test_policy_from_equipment(self, equipment: EquipmentSpec) -> None:
        policy = TemperaturePolicy.from_equipment(equipment)
        assert policy.min_safe == equipment.min_operating_temp_c
        assert policy.max_safe == equipment.max_operating_temp_c
        assert policy.throttle_threshold == equipment.throttle_temp_c
        assert policy.shutdown_threshold == equipment.shutdown_temp_c

    def test_policy_invalid_thresholds_raises(self) -> None:
        with pytest.raises(ValueError, match="Min safe"):
            TemperaturePolicy(min_safe=Decimal("90"), max_safe=Decimal("80"))

    def test_policy_throttle_exceeds_shutdown_raises(self) -> None:
        with pytest.raises(ValueError, match="Throttle"):
            TemperaturePolicy(
                throttle_threshold=Decimal("95"),
                shutdown_threshold=Decimal("90"),
            )

    def test_policy_alert_exceeds_throttle_raises(self) -> None:
        with pytest.raises(ValueError, match="Alert"):
            TemperaturePolicy(
                alert_threshold=Decimal("80"),
                throttle_threshold=Decimal("75"),
            )


# ── Deliverable 8: Mining Financial Integration ──


class TestMiningFinancialIntegration:
    """Tests for mining financial integration."""

    def test_mining_financial_entry_creation(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        result = sim.run_simulation(mining_session_config)
        entry = MiningFinancialEntry.from_result(result, Decimal("50000"))
        assert entry.is_mining is True
        assert entry.revenue_btc == result.daily_net_revenue_btc
        assert entry.electricity_cost == result.daily_electricity_cost
        assert entry.depreciation_cost == result.daily_depreciation
        assert entry.entry_type == "mining_daily_revenue"

    def test_mining_financial_entry_distinguishes_from_trading(self) -> None:
        entry = MiningFinancialEntry(
            session_id=MiningSessionId.generate(),
            revenue_btc=Decimal("0.001"),
            electricity_cost=Decimal("5"),
            depreciation_cost=Decimal("1"),
            pool_fee_btc=Decimal("0.00001"),
            net_profit_fiat=Decimal("44"),
        )
        assert entry.is_mining is True

    def test_mining_financial_entry_naive_timestamp_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            MiningFinancialEntry(
                session_id=MiningSessionId.generate(),
                revenue_btc=Decimal("0.001"),
                electricity_cost=Decimal("5"),
                depreciation_cost=Decimal("1"),
                pool_fee_btc=Decimal("0.00001"),
                net_profit_fiat=Decimal("44"),
                timestamp=datetime.now(),
            )


# ── Deliverable 9: Failure Simulation ──


class TestFailureSimulation:
    """Tests for failure simulation."""

    def test_failure_event_creation(self, equipment: EquipmentSpec) -> None:
        event = FailureEvent.create(
            equipment_id=equipment.equipment_id,
            failure_type=FailureType.OVERHEAT,
            start_time=datetime.now(UTC),
            description="Overheating detected",
        )
        assert event.failure_type == FailureType.OVERHEAT
        assert event.is_resolved is False

    def test_failure_event_resolve(self, equipment: EquipmentSpec) -> None:
        event = FailureEvent.create(
            equipment_id=equipment.equipment_id,
            failure_type=FailureType.FAN_FAILURE,
            start_time=datetime.now(UTC),
        )
        resolved = event.resolve()
        assert resolved.is_resolved is True
        assert resolved.end_time is not None

    def test_failure_event_already_resolved_raises(self, equipment: EquipmentSpec) -> None:
        event = FailureEvent(
            event_id=FailureEventId.generate(),
            equipment_id=equipment.equipment_id,
            failure_type=FailureType.POWER_SUPPLY_FAILURE,
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(hours=1),
        )
        with pytest.raises(ValueError, match="already resolved"):
            event.resolve()

    def test_failure_event_naive_start_time_raises(self, equipment: EquipmentSpec) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FailureEvent.create(
                equipment_id=equipment.equipment_id,
                failure_type=FailureType.NETWORK_OUTAGE,
                start_time=datetime.now(),
            )

    def test_failure_event_end_before_start_raises(self, equipment: EquipmentSpec) -> None:
        with pytest.raises(ValueError, match="end_time"):
            FailureEvent(
                event_id=FailureEventId.generate(),
                equipment_id=equipment.equipment_id,
                failure_type=FailureType.COOLING_FAILURE,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC) - timedelta(hours=1),
            )

    def test_failure_event_duration(self, equipment: EquipmentSpec) -> None:
        start = datetime.now(UTC)
        end = start + timedelta(hours=2)
        event = FailureEvent(
            event_id=FailureEventId.generate(),
            equipment_id=equipment.equipment_id,
            failure_type=FailureType.HASHBOARD_FAILURE,
            start_time=start,
            end_time=end,
        )
        assert event.duration == timedelta(hours=2)
        assert event.duration_seconds == Decimal("7200")

    def test_simulator_inject_failure(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        event = sim.inject_failure(
            mining_session_config.session_id,
            mining_session_config,
            FailureType.OVERHEAT,
        )
        assert event.failure_type == FailureType.OVERHEAT
        assert sim.safety_state.failure_count == 1

    def test_simulator_resolve_failure(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        event = sim.inject_failure(
            mining_session_config.session_id,
            mining_session_config,
            FailureType.FAN_FAILURE,
        )
        resolved = sim.resolve_failure(event.event_id)
        assert resolved is not None
        assert resolved.is_resolved is True

    def test_simulator_resolve_unknown_failure_returns_none(self) -> None:

        sim = MiningSimulator()
        result = sim.resolve_failure(FailureEventId.generate())
        assert result is None

    def test_all_failure_types(self) -> None:
        """Per AD-023: fault injection covers multiple failure types."""
        for ft in FailureType:
            assert ft.value  # all enum values are non-empty strings


# ── Deliverable 10: Controlled Adapter Interfaces ──


class TestControlledAdapters:
    """Tests for controlled adapter interfaces and safety state."""

    def test_mining_operation_status_enum(self) -> None:
        assert MiningOperationStatus.SIMULATION_ONLY.value == "simulation_only"
        assert MiningOperationStatus.AUTHORIZED.value == "authorized"
        assert MiningOperationStatus.SUSPENDED.value == "suspended"
        assert MiningOperationStatus.EMERGENCY_STOP.value == "emergency_stop"

    def test_mining_safety_state_default(self) -> None:
        state = MiningSafetyState()
        assert state.emergency_stop_active is False
        assert state.physical_operations_authorized is False
        assert state.is_safe is True
        assert state.failure_count == 0

    def test_mining_safety_state_emergency_stop(self) -> None:
        state = MiningSafetyState()
        state.trigger_emergency_stop()
        assert state.emergency_stop_active is True
        assert state.is_safe is False

    def test_mining_safety_state_clear_emergency_stop(self) -> None:
        state = MiningSafetyState()
        state.trigger_emergency_stop()
        state.clear_emergency_stop("owner")
        assert state.emergency_stop_active is False
        assert state.is_safe is True

    def test_mining_safety_state_clear_requires_authorized_by(self) -> None:
        state = MiningSafetyState()
        state.trigger_emergency_stop()
        with pytest.raises(ValueError, match="authorized_by"):
            state.clear_emergency_stop("")

    def test_mining_safety_state_authorize_physical(self) -> None:
        state = MiningSafetyState()
        state.authorize_physical_operations("owner")
        assert state.physical_operations_authorized is True

    def test_mining_safety_state_authorize_blocked_by_emergency_stop(self) -> None:
        state = MiningSafetyState()
        state.trigger_emergency_stop()
        with pytest.raises(PermissionError, match="emergency stop"):
            state.authorize_physical_operations("owner")

    def test_mining_safety_state_revoke_physical(self) -> None:
        state = MiningSafetyState()
        state.authorize_physical_operations("owner")
        state.revoke_physical_operations()
        assert state.physical_operations_authorized is False

    def test_mining_safety_state_add_failure(self) -> None:
        state = MiningSafetyState()
        event = FailureEvent.create(
            equipment_id=MiningEquipmentId.generate(),
            failure_type=FailureType.OVERHEAT,
            start_time=datetime.now(UTC),
        )
        state.add_failure(event)
        assert state.failure_count == 1
        assert state.is_safe is False  # overheat makes it unsafe

    def test_mining_safety_state_resolve_failure(self) -> None:
        state = MiningSafetyState()
        event = FailureEvent.create(
            equipment_id=MiningEquipmentId.generate(),
            failure_type=FailureType.OVERHEAT,
            start_time=datetime.now(UTC),
        )
        state.add_failure(event)
        assert state.is_safe is False
        resolved = state.resolve_failure(event.event_id)
        assert resolved is not None
        assert resolved.is_resolved is True
        # Still in active_failures list but resolved
        assert state.failure_count == 1

    def test_mining_safety_state_resolve_unknown_returns_none(self) -> None:
        state = MiningSafetyState()
        result = state.resolve_failure(FailureEventId.generate())
        assert result is None

    def test_mining_safety_limits_default(self) -> None:
        limits = MiningSafetyLimits()
        assert limits.max_temperature_c == Decimal("90")
        assert limits.max_power_w == Decimal("5000")

    def test_mining_safety_limits_check_temperature(self) -> None:
        limits = MiningSafetyLimits()
        assert limits.check_temperature(Decimal("80")) is True
        assert limits.check_temperature(Decimal("95")) is False

    def test_mining_safety_limits_check_power(self) -> None:
        limits = MiningSafetyLimits()
        assert limits.check_power(Decimal("3000")) is True
        assert limits.check_power(Decimal("6000")) is False

    def test_mining_safety_limits_check_all(self) -> None:
        limits = MiningSafetyLimits()
        assert limits.check_all(Decimal("80"), Decimal("3000"), Decimal("1"), Decimal("10")) is True
        assert (
            limits.check_all(Decimal("95"), Decimal("3000"), Decimal("1"), Decimal("10")) is False
        )

    def test_mining_safety_limits_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Max temp"):
            MiningSafetyLimits(max_temperature_c=Decimal("0"))
        with pytest.raises(ValueError, match="Max power"):
            MiningSafetyLimits(max_power_w=Decimal("0"))
        with pytest.raises(ValueError, match="Max downtime"):
            MiningSafetyLimits(max_downtime_pct=Decimal("150"))

    def test_simulator_check_safety_limits(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:

        sim = MiningSimulator()
        limits = MiningSafetyLimits()
        assert (
            sim.check_safety_limits(
                limits, Decimal("80"), Decimal("3000"), Decimal("1"), Decimal("10")
            )
            is True
        )
        assert (
            sim.check_safety_limits(
                limits, Decimal("95"), Decimal("3000"), Decimal("1"), Decimal("10")
            )
            is False
        )


# ── Cross-cutting: Mining Session Config ──


class TestMiningSessionConfig:
    """Tests for the mining session configuration."""

    def test_config_creation(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:
        assert mining_session_config.btc_price == Decimal("50000")
        assert mining_session_config.uptime_pct == Decimal("95")
        assert mining_session_config.session_id is not None

    def test_config_invalid_btc_price_raises(
        self,
        equipment: EquipmentSpec,
        pool: PoolConfig,
        electricity: ElectricityConfig,
        network_difficulty: NetworkDifficulty,
        block_reward: BlockReward,
    ) -> None:
        with pytest.raises(ValueError, match="BTC price"):
            MiningSessionConfig.create(
                equipment=equipment,
                pool=pool,
                electricity=electricity,
                network_difficulty=network_difficulty,
                block_reward=block_reward,
                btc_price="0",
            )

    def test_config_invalid_uptime_raises(
        self,
        equipment: EquipmentSpec,
        pool: PoolConfig,
        electricity: ElectricityConfig,
        network_difficulty: NetworkDifficulty,
        block_reward: BlockReward,
    ) -> None:
        with pytest.raises(ValueError, match="Uptime"):
            MiningSessionConfig.create(
                equipment=equipment,
                pool=pool,
                electricity=electricity,
                network_difficulty=network_difficulty,
                block_reward=block_reward,
                btc_price="50000",
                uptime_pct="150",
            )

    def test_config_auto_creates_depreciation(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:
        dep = mining_session_config.depreciation
        assert dep.initial_cost == Decimal("5000")
        assert dep.salvage_value == Decimal("500")
        assert dep.useful_life_months == 36

    def test_config_auto_creates_temperature_policy(
        self,
        mining_session_config: MiningSessionConfig,
    ) -> None:
        pol = mining_session_config.temperature_policy
        assert pol is not None
        assert pol.shutdown_threshold == Decimal("85")


# ── Cross-cutting: Safety — physical operations not activated ──


class TestPhysicalOperationsNotActivated:
    """Verify that simulation does NOT activate physical mining.

    Per AD-015: real hardware and pool integration require explicit approval
    and safety controls. Simulation must NOT activate physical operations.
    Per Section 09.2: physical operations remain separately authorized.
    """

    def test_simulator_does_not_authorize_physical(self) -> None:

        sim = MiningSimulator()
        assert sim.safety_state.physical_operations_authorized is False

    def test_simulator_emergency_stop_blocks(self) -> None:

        sim = MiningSimulator()
        sim.trigger_emergency_stop()
        assert sim.safety_state.is_safe is False

    def test_physical_authorization_requires_authorized_by(self) -> None:
        state = MiningSafetyState()
        with pytest.raises(ValueError, match="authorized_by"):
            state.authorize_physical_operations("")

    def test_physical_authorization_blocked_by_emergency(self) -> None:
        state = MiningSafetyState()
        state.trigger_emergency_stop()
        with pytest.raises(PermissionError, match="emergency stop"):
            state.authorize_physical_operations("owner")
