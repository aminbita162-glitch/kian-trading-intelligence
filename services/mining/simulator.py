"""Mining simulator service for Kian Trading Intelligence.

Per Section 09.1: Mining Simulation — model hash rate, network difficulty,
expected rewards, pool fees, electricity costs, equipment efficiency, hardware
depreciation, temperature, downtime, net profitability and uncertainty.

Per AD-015: begin with simulation and profitability validation. Real hardware
and pool integration require explicit approval and safety controls.

Per AD-023: deterministic simulation, mining simulation, and repeatable
verification before live operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from threading import Lock

from contracts.mining import (
    FailureEvent,
    FailureEventId,
    FailureType,
    HashRate,
    MiningHardwareStatus,
    MiningSafetyLimits,
    MiningSafetyState,
    MiningSessionConfig,
    MiningSessionId,
    MiningSimulationResult,
    SimulatedPoolAdapter,
    TelemetryHistory,
    TelemetryId,
    TelemetryReading,
    TemperatureAction,
)
from contracts.mode import OperatingModeConfig

SECONDS_PER_DAY = Decimal(86400)
HOURS_PER_DAY = Decimal(24)
DAYS_PER_MONTH = Decimal(30)


class MiningSimulator:
    """Deterministic mining profitability simulator.

    Per AD-023: deterministic simulation — same inputs produce same outputs.
    Per AD-015: simulation only; does NOT activate physical mining.
    Per Section 09.1: models all profitability factors with uncertainty.

    The simulator is thread-safe — multiple sessions can run concurrently.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._results: dict[str, MiningSimulationResult] = {}
        self._sessions: dict[str, MiningSessionConfig] = {}
        self._telemetry_histories: dict[str, TelemetryHistory] = {}
        self._safety_state = MiningSafetyState()
        self._pool: SimulatedPoolAdapter | None = None

    @property
    def safety_state(self) -> MiningSafetyState:
        return self._safety_state

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    @property
    def is_simulation(self) -> bool:
        return True

    def run_simulation(self, config: MiningSessionConfig) -> MiningSimulationResult:
        """Run a deterministic mining profitability simulation.

        Per Section 09.1: model hash rate, network difficulty, expected
        rewards, pool fees, electricity costs, equipment efficiency, hardware
        depreciation, temperature, downtime, net profitability, uncertainty.

        Per AD-023: deterministic — same config produces same result.

        Args:
            config: Mining session configuration.

        Returns:
            MiningSimulationResult with profitability metrics.
        """
        with self._lock:
            # Prevent simulation if emergency stop is active
            if self._safety_state.emergency_stop_active:
                raise PermissionError(
                    "Cannot run mining simulation while emergency stop is active."
                )

            # Verify simulation mode (not live)
            mode_config = OperatingModeConfig()
            if mode_config.is_live:
                raise PermissionError(
                    "Mining simulation must not run in LIVE mode. "
                    "Use SIMULATION mode for mining profitability validation."
                )

            self._sessions[str(config.session_id)] = config

            # 1. Hash rate and reward model (Deliverable 2)
            hash_rate_hps = config.equipment.hash_rate.hash_per_second
            difficulty = config.network_difficulty.value
            reward = config.block_reward.reward_btc

            # Expected blocks per day = (hash_rate / difficulty) * 2^32 / seconds
            # Simplified deterministic model:
            # blocks_per_day = hash_rate_hps * SECONDS_PER_DAY / (difficulty * 2^32)
            # Using a simplified factor for determinism:
            HASH_FACTOR = Decimal("4295098368")  # 2^32 approximation
            blocks_per_day = (hash_rate_hps * SECONDS_PER_DAY) / (difficulty * HASH_FACTOR)
            gross_daily_btc = blocks_per_day * reward

            # 2. Pool fees (Deliverable 5)
            pool_fee_fraction = config.pool.fee_fraction
            pool_fee_btc = gross_daily_btc * pool_fee_fraction
            net_daily_btc = gross_daily_btc - pool_fee_btc

            # 3. Electricity cost (Deliverable 3)
            daily_electricity = config.electricity.daily_cost(
                config.equipment.power_consumption_w,
                config.uptime_pct,
            )

            # 4. Depreciation (Deliverable 4)
            daily_depreciation = config.depreciation.daily_depreciation

            # 5. Net profitability in fiat (Deliverable 1)
            daily_revenue_fiat = net_daily_btc * config.btc_price
            daily_net_profit = daily_revenue_fiat - daily_electricity - daily_depreciation
            is_profitable = daily_net_profit > Decimal(0)

            # 6. Break-even BTC price (Deliverable 1)
            if net_daily_btc > 0:
                daily_costs_fiat = daily_electricity + daily_depreciation
                break_even = daily_costs_fiat / net_daily_btc
            else:
                break_even = Decimal(0)

            # 7. Equipment efficiency (Deliverable 2)
            efficiency = config.equipment.efficiency_j_per_th

            # 8. Uncertainty range (Section 09.1: uncertainty)
            # ±15% around the estimate for deterministic uncertainty modeling
            UNCERTAINTY_FACTOR = Decimal("0.15")
            uncertainty_low = daily_net_profit * (Decimal(1) - UNCERTAINTY_FACTOR)
            uncertainty_high = daily_net_profit * (Decimal(1) + UNCERTAINTY_FACTOR)

            result = MiningSimulationResult(
                session_id=config.session_id,
                daily_gross_revenue_btc=gross_daily_btc,
                daily_pool_fee_btc=pool_fee_btc,
                daily_net_revenue_btc=net_daily_btc,
                daily_electricity_cost=daily_electricity,
                daily_depreciation=daily_depreciation,
                daily_net_profit=daily_net_profit,
                is_profitable=is_profitable,
                break_even_btc_price=break_even,
                daily_btc_mined=net_daily_btc,
                efficiency_j_per_th=efficiency,
                uncertainty_range=(uncertainty_low, uncertainty_high),
                is_simulation=True,
            )

            self._results[str(config.session_id)] = result
            return result

    def get_result(self, session_id: MiningSessionId) -> MiningSimulationResult | None:
        """Get a simulation result by session ID."""
        with self._lock:
            return self._results.get(str(session_id))

    def generate_telemetry(
        self,
        session_id: MiningSessionId,
        config: MiningSessionConfig,
        elapsed_hours: Decimal = Decimal("1"),
    ) -> TelemetryReading:
        """Generate simulated telemetry for a mining session.

        Per Section 09.2: reliable telemetry.
        Per AD-023: deterministic simulation.

        Generates deterministic telemetry based on the session config and
        elapsed time. Temperature is modeled with a deterministic offset
        based on power consumption and uptime.

        Args:
            session_id: Mining session identifier.
            config: Session configuration.
            elapsed_hours: Elapsed hours since session start.

        Returns:
            TelemetryReading with simulated hardware metrics.
        """
        with self._lock:
            # Deterministic temperature model
            # Base temp + (power / 100) * uptime_factor + elapsed_factor
            POWER_DIVISOR = Decimal("100")
            base_temp = Decimal("35")
            power_factor = config.equipment.power_consumption_w / POWER_DIVISOR
            uptime_factor = config.uptime_pct / Decimal(100)
            elapsed_factor = elapsed_hours * Decimal("2")
            temperature = base_temp + power_factor * uptime_factor + elapsed_factor

            # Apply temperature policy
            action = config.temperature_policy.evaluate(temperature)
            if action is TemperatureAction.SHUTDOWN:
                temperature = config.temperature_policy.shutdown_threshold

            # Hash rate (may be throttled)
            hash_rate = config.equipment.hash_rate
            if action is TemperatureAction.THROTTLE:
                # Throttle to 70% of nominal
                THROTTLE_FACTOR = Decimal("0.70")
                throttled_value = hash_rate.value * THROTTLE_FACTOR
                hash_rate = HashRate(throttled_value, hash_rate.unit)

            # Power draw (may be reduced when throttled)
            power_w = config.equipment.power_consumption_w
            if action is TemperatureAction.THROTTLE:
                THROTTLE_POWER = Decimal("0.85")
                power_w = power_w * THROTTLE_POWER

            # Fan speed scales with temperature
            FAN_BASE = Decimal("1500")
            FAN_MAX = Decimal("4500")
            TEMP_SCALE = Decimal("50")
            temp_scale_factor = min(temperature / TEMP_SCALE, Decimal(1))
            fan_speed = FAN_BASE + (FAN_MAX - FAN_BASE) * temp_scale_factor

            # Status — determine hardware status from temperature action
            IDLE_TEMP_THRESHOLD = Decimal("40")
            if action is TemperatureAction.SHUTDOWN:
                status = MiningHardwareStatus.OFFLINE
            elif action is TemperatureAction.THROTTLE:
                status = MiningHardwareStatus.THROTTLED
            elif temperature > config.temperature_policy.max_safe:
                status = MiningHardwareStatus.OVERHEATING
            elif temperature < IDLE_TEMP_THRESHOLD:
                status = MiningHardwareStatus.IDLE
            else:
                status = MiningHardwareStatus.RUNNING

            reading = TelemetryReading(
                reading_id=TelemetryId.generate(),
                equipment_id=config.equipment.equipment_id,
                timestamp=datetime.now(UTC),
                temperature_c=temperature,
                hash_rate=hash_rate,
                power_w=power_w,
                fan_speed_rpm=fan_speed,
                status=status,
            )

            # Store telemetry history
            session_key = str(session_id)
            if session_key not in self._telemetry_histories:
                self._telemetry_histories[session_key] = TelemetryHistory(
                    equipment_id=config.equipment.equipment_id,
                )
            self._telemetry_histories[session_key].add(reading)

            return reading

    def get_telemetry_history(self, session_id: MiningSessionId) -> TelemetryHistory | None:
        """Get the telemetry history for a session."""
        with self._lock:
            return self._telemetry_histories.get(str(session_id))

    def inject_failure(
        self,
        session_id: MiningSessionId,
        config: MiningSessionConfig,
        failure_type: FailureType,
        start_time: datetime | None = None,
    ) -> FailureEvent:
        """Inject a hardware failure into a running simulation.

        Per AD-023: fault injection and deterministic simulation.
        Per Section 09.2: failure handling.

        Args:
            session_id: Mining session identifier.
            config: Session configuration.
            failure_type: Type of failure to inject.
            start_time: Failure start time (defaults to now).

        Returns:
            The created FailureEvent.
        """
        with self._lock:
            event = FailureEvent.create(
                equipment_id=config.equipment.equipment_id,
                failure_type=failure_type,
                start_time=start_time or datetime.now(UTC),
                description=f"Simulated {failure_type.value} failure for session {session_id}",
            )
            self._safety_state.add_failure(event)
            return event

    def resolve_failure(self, event_id: FailureEventId) -> FailureEvent | None:
        """Resolve a previously injected failure event."""
        with self._lock:
            return self._safety_state.resolve_failure(event_id)

    def trigger_emergency_stop(self) -> None:
        """Trigger an emergency stop for all mining operations.

        Per AD-013: emergency stop must block new operations.
        Per Section 09.2: safety limits.
        """
        with self._lock:
            self._safety_state.trigger_emergency_stop()

    def clear_emergency_stop(self, authorized_by: str) -> None:
        """Clear an emergency stop (requires explicit authorization).

        Per AD-015: explicit authorization for physical operations.
        """
        with self._lock:
            self._safety_state.clear_emergency_stop(authorized_by)

    def get_safety_state(self) -> MiningSafetyState:
        """Get the current mining safety state."""
        with self._lock:
            return self._safety_state

    def check_safety_limits(
        self,
        limits: MiningSafetyLimits,
        temperature_c: Decimal,
        power_w: Decimal,
        hash_rate: Decimal,
        downtime_pct: Decimal,
    ) -> bool:
        """Check whether current operating parameters are within safety limits.

        Per Section 09.2: safety limits.
        Per AD-013: enforce hard limits.
        """
        return limits.check_all(temperature_c, power_w, hash_rate, downtime_pct)

    def reset(self) -> None:
        """Reset all simulator state (for testing)."""
        with self._lock:
            self._results.clear()
            self._sessions.clear()
            self._telemetry_histories.clear()
            self._safety_state = MiningSafetyState()
            self._pool = None
