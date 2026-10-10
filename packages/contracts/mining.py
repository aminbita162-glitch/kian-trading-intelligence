"""Mining contracts for Kian Trading Intelligence.

Per Section 09 (Mining Operations):
- 09.1: Model hash rate; network difficulty; expected rewards; pool fees;
  electricity costs; equipment efficiency; hardware depreciation; temperature;
  downtime; net profitability and uncertainty.
- 09.2: Physical integration requires approved adapter; verified operator
  authority; safety limits; reliable telemetry; failure handling; explicit
  authorization. The MacBook is a control interface, not the assumed mining
  hardware. Mining financial records must remain distinguishable from trading
  records.

Per AD-015: begin with simulation and profitability validation. Real hardware
and pool integration require explicit approval and safety controls.

Per AD-023: deterministic simulation, mining simulation, and repeatable
verification before live operations.

Per AD-004 Section 04.4: Mining Operations Agent responsibilities — simulation,
profitability assessment, pool/hardware coordination, safety telemetry. Prohibited:
unrestricted trading-account access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

# ── Enums ──


class HashRateUnit(StrEnum):
    """Unit of measure for hash rate."""

    HASH_PER_S = "H/s"
    KILOHASH_PER_S = "kH/s"
    MEGAHASH_PER_S = "MH/s"
    GIGAHASH_PER_S = "GH/s"
    TERAHASH_PER_S = "TH/s"
    PETAHASH_PER_S = "PH/s"


class MiningHardwareStatus(StrEnum):
    """Operational status of mining hardware."""

    IDLE = "idle"
    RUNNING = "running"
    THROTTLED = "throttled"
    OVERHEATING = "overheating"
    FAILED = "failed"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class PoolPayoutScheme(StrEnum):
    """Pool payout scheme per Section 09.1."""

    PPS = "pps"  # Pay Per Share
    PPLNS = "pplns"  # Pay Per Last N Shares
    PROP = "prop"  # Proportional
    SOLO = "solo"  # Solo mining


class FailureType(StrEnum):
    """Types of hardware failures for failure simulation.

    Per Section 09.2: failure handling.
    Per AD-023: fault injection and deterministic simulation.
    """

    OVERHEAT = "overheat"
    HASHBOARD_FAILURE = "hashboard_failure"
    POWER_SUPPLY_FAILURE = "power_supply_failure"
    NETWORK_OUTAGE = "network_outage"
    COOLING_FAILURE = "cooling_failure"
    FAN_FAILURE = "fan_failure"
    UNKNOWN = "unknown"


class MiningOperationStatus(StrEnum):
    """Authorization status for physical mining operations.

    Per AD-015: real hardware and pool integration require explicit approval
    and safety controls. Physical operations remain separately authorized.
    """

    SIMULATION_ONLY = "simulation_only"
    AUTHORIZED = "authorized"
    SUSPENDED = "suspended"
    EMERGENCY_STOP = "emergency_stop"


class TemperatureAction(StrEnum):
    """Action triggered by a temperature policy violation."""

    NONE = "none"
    THROTTLE = "throttle"
    SHUTDOWN = "shutdown"
    ALERT = "alert"


# ── Stable Identity Value Objects ──


@dataclass(frozen=True)
class MiningEquipmentId:
    """Stable identity for a piece of mining equipment."""

    value: UUID

    @classmethod
    def generate(cls) -> MiningEquipmentId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class MiningSessionId:
    """Stable identity for a mining simulation session."""

    value: UUID

    @classmethod
    def generate(cls) -> MiningSessionId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class TelemetryId:
    """Stable identity for a telemetry reading."""

    value: UUID

    @classmethod
    def generate(cls) -> TelemetryId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PoolAdapterId:
    """Stable identity for a pool adapter instance."""

    value: UUID

    @classmethod
    def generate(cls) -> PoolAdapterId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class HardwareAdapterId:
    """Stable identity for a hardware adapter instance."""

    value: UUID

    @classmethod
    def generate(cls) -> HardwareAdapterId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class FailureEventId:
    """Stable identity for a failure event."""

    value: UUID

    @classmethod
    def generate(cls) -> FailureEventId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


# ── Hash Rate Model (Deliverable 2) ──


# Conversion factors to base unit (H/s)
_UNIT_TO_HASH_PER_S: dict[HashRateUnit, Decimal] = {
    HashRateUnit.HASH_PER_S: Decimal("1"),
    HashRateUnit.KILOHASH_PER_S: Decimal("1000"),
    HashRateUnit.MEGAHASH_PER_S: Decimal("1000000"),
    HashRateUnit.GIGAHASH_PER_S: Decimal("1000000000"),
    HashRateUnit.TERAHASH_PER_S: Decimal("1000000000000"),
    HashRateUnit.PETAHASH_PER_S: Decimal("1000000000000000"),
}


@dataclass(frozen=True)
class HashRate:
    """Hash rate model per Section 09.1.

    Stores the hash rate as a decimal value with an explicit unit. Provides
    conversion to a common base unit (H/s) for deterministic calculations.

    Per AD-023: deterministic simulation — same inputs produce same outputs.
    """

    value: Decimal
    unit: HashRateUnit

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("Hash rate value must be non-negative.")

    @classmethod
    def from_str(cls, value: str, unit: HashRateUnit) -> HashRate:
        return cls(Decimal(value), unit)

    @property
    def hash_per_second(self) -> Decimal:
        """Convert to base unit (H/s) for calculations."""
        factor = _UNIT_TO_HASH_PER_S[self.unit]
        return self.value * factor

    def to_unit(self, unit: HashRateUnit) -> HashRate:
        """Convert to a different unit."""
        hps = self.hash_per_second
        target_factor = _UNIT_TO_HASH_PER_S[unit]
        return HashRate(hps / target_factor, unit)

    def __str__(self) -> str:
        return f"{self.value} {self.unit.value}"


# ── Network Difficulty Model (Deliverable 2) ──


@dataclass(frozen=True)
class NetworkDifficulty:
    """Network difficulty model per Section 09.1.

    Network difficulty determines how difficult it is to find a block.
    Higher difficulty means lower expected rewards for the same hash rate.
    """

    value: Decimal

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("Network difficulty must be positive.")

    @classmethod
    def from_str(cls, value: str) -> NetworkDifficulty:
        return cls(Decimal(value))


# ── Block Reward Model (Deliverable 2) ──


@dataclass(frozen=True)
class BlockReward:
    """Block reward model per Section 09.1.

    The reward in BTC for finding a block. May include transaction fees.
    """

    reward_btc: Decimal

    def __post_init__(self) -> None:
        if self.reward_btc <= 0:
            raise ValueError("Block reward must be positive.")

    @classmethod
    def from_str(cls, reward_btc: str) -> BlockReward:
        return cls(Decimal(reward_btc))


# ── Equipment Specification (Deliverable 1, 2) ──


@dataclass(frozen=True)
class EquipmentSpec:
    """Specification for mining hardware.

    Per Section 09.1: equipment efficiency, hardware depreciation, temperature.
    Per Section 09.2: physical integration requires approved adapter and safety.

    Attributes:
        equipment_id: Stable unique identifier.
        name: Human-readable equipment name.
        hash_rate: Nominal hash rate.
        power_consumption_w: Power draw in watts at full load.
        cost: Purchase cost in fiat currency.
        useful_life_months: Useful life for depreciation.
        salvage_value: Salvage value after useful life.
        min_operating_temp_c: Minimum safe operating temperature (Celsius).
        max_operating_temp_c: Maximum safe operating temperature (Celsius).
        throttle_temp_c: Temperature at which throttling begins.
        shutdown_temp_c: Temperature at which shutdown is triggered.
    """

    equipment_id: MiningEquipmentId
    name: str
    hash_rate: HashRate
    power_consumption_w: Decimal
    cost: Decimal
    useful_life_months: int
    salvage_value: Decimal = Decimal("0")
    min_operating_temp_c: Decimal = Decimal("0")
    max_operating_temp_c: Decimal = Decimal("85")
    throttle_temp_c: Decimal = Decimal("75")
    shutdown_temp_c: Decimal = Decimal("90")

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Equipment name must not be empty.")
        if self.power_consumption_w <= 0:
            raise ValueError("Power consumption must be positive.")
        if self.cost < 0:
            raise ValueError("Cost must be non-negative.")
        if self.useful_life_months <= 0:
            raise ValueError("Useful life must be positive.")
        if self.salvage_value < 0:
            raise ValueError("Salvage value must be non-negative.")
        if self.salvage_value > self.cost:
            raise ValueError("Salvage value must not exceed cost.")
        if self.min_operating_temp_c >= self.max_operating_temp_c:
            raise ValueError("Min operating temp must be below max operating temp.")
        if self.throttle_temp_c > self.shutdown_temp_c:
            raise ValueError("Throttle temp must not exceed shutdown temp.")

    @property
    def efficiency_j_per_th(self) -> Decimal:
        """Energy efficiency in Joules per Terahash."""
        if self.hash_rate.value == 0:
            return Decimal(0)
        hps = self.hash_rate.hash_per_second
        thps = hps / Decimal("1000000000000")
        if thps == 0:
            return Decimal(0)
        return self.power_consumption_w / thps

    @classmethod
    def create(  # noqa: PLR0913
        cls,
        *,
        name: str,
        hash_rate_value: str,
        hash_rate_unit: HashRateUnit,
        power_consumption_w: str,
        cost: str,
        useful_life_months: int,
        salvage_value: str = "0",
        min_operating_temp_c: str = "0",
        max_operating_temp_c: str = "85",
        throttle_temp_c: str = "75",
        shutdown_temp_c: str = "90",
    ) -> EquipmentSpec:
        return cls(
            equipment_id=MiningEquipmentId.generate(),
            name=name,
            hash_rate=HashRate(Decimal(hash_rate_value), hash_rate_unit),
            power_consumption_w=Decimal(power_consumption_w),
            cost=Decimal(cost),
            useful_life_months=useful_life_months,
            salvage_value=Decimal(salvage_value),
            min_operating_temp_c=Decimal(min_operating_temp_c),
            max_operating_temp_c=Decimal(max_operating_temp_c),
            throttle_temp_c=Decimal(throttle_temp_c),
            shutdown_temp_c=Decimal(shutdown_temp_c),
        )


# ── Electricity Cost Model (Deliverable 3) ──


@dataclass(frozen=True)
class ElectricityConfig:
    """Electricity cost configuration per Section 09.1.

    Per Section 09.1: electricity costs.

    Attributes:
        rate_per_kwh: Cost per kilowatt-hour in fiat currency.
        currency: Fiat currency code (e.g., "USD", "EUR").
    """

    rate_per_kwh: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.rate_per_kwh < 0:
            raise ValueError("Electricity rate must be non-negative.")
        if not self.currency:
            raise ValueError("Currency must not be empty.")

    @classmethod
    def from_str(cls, rate_per_kwh: str, currency: str = "USD") -> ElectricityConfig:
        return cls(Decimal(rate_per_kwh), currency)

    def daily_cost(self, power_consumption_w: Decimal, uptime_pct: Decimal) -> Decimal:
        """Calculate daily electricity cost.

        Args:
            power_consumption_w: Power draw in watts.
            uptime_pct: Uptime percentage (0-100).

        Returns:
            Daily cost in the configured fiat currency.
        """
        MAX_UPTIME_PCT = Decimal(100)
        if uptime_pct < 0 or uptime_pct > MAX_UPTIME_PCT:
            raise ValueError("Uptime percentage must be between 0 and 100.")
        if power_consumption_w < 0:
            raise ValueError("Power consumption must be non-negative.")
        HOURS_PER_DAY = Decimal(24)
        uptime_fraction = uptime_pct / MAX_UPTIME_PCT
        kwh_per_day = (power_consumption_w / Decimal(1000)) * HOURS_PER_DAY * uptime_fraction
        return kwh_per_day * self.rate_per_kwh

    def monthly_cost(self, power_consumption_w: Decimal, uptime_pct: Decimal) -> Decimal:
        """Calculate monthly (30-day) electricity cost."""
        return self.daily_cost(power_consumption_w, uptime_pct) * Decimal(30)


# ── Depreciation Model (Deliverable 4) ──


@dataclass(frozen=True)
class DepreciationConfig:
    """Hardware depreciation configuration per Section 09.1.

    Per Section 09.1: hardware depreciation. Uses straight-line depreciation.

    Attributes:
        initial_cost: Purchase cost of the equipment.
        salvage_value: Value at end of useful life.
        useful_life_months: Useful life in months.
    """

    initial_cost: Decimal
    salvage_value: Decimal = Decimal("0")
    useful_life_months: int = 36

    def __post_init__(self) -> None:
        if self.initial_cost < 0:
            raise ValueError("Initial cost must be non-negative.")
        if self.salvage_value < 0:
            raise ValueError("Salvage value must be non-negative.")
        if self.salvage_value > self.initial_cost:
            raise ValueError("Salvage value must not exceed initial cost.")
        if self.useful_life_months <= 0:
            raise ValueError("Useful life must be positive.")

    @classmethod
    def from_equipment(cls, equipment: EquipmentSpec) -> DepreciationConfig:
        """Create depreciation config from an equipment spec."""
        return cls(
            initial_cost=equipment.cost,
            salvage_value=equipment.salvage_value,
            useful_life_months=equipment.useful_life_months,
        )

    @property
    def monthly_depreciation(self) -> Decimal:
        """Monthly depreciation expense (straight-line)."""
        depreciable_amount = self.initial_cost - self.salvage_value
        return depreciable_amount / Decimal(self.useful_life_months)

    @property
    def daily_depreciation(self) -> Decimal:
        """Daily depreciation expense (30-day month)."""
        return self.monthly_depreciation / Decimal(30)


# ── Pool Configuration (Deliverable 5) ──


@dataclass(frozen=True)
class PoolConfig:
    """Mining pool configuration per Section 09.1.

    Per Section 09.1: pool fees.
    Per Section 09.2: physical integration requires approved adapter.

    Attributes:
        pool_id: Stable unique identifier.
        name: Pool name.
        url: Pool endpoint URL (simulation only).
        fee_pct: Pool fee as a percentage (0-100).
        payout_scheme: Payout scheme (PPS, PPLNS, etc.).
        min_payout: Minimum payout amount in BTC.
    """

    pool_id: PoolAdapterId
    name: str
    url: str
    fee_pct: Decimal
    payout_scheme: PoolPayoutScheme = PoolPayoutScheme.PPS
    min_payout: Decimal = Decimal("0.001")

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Pool name must not be empty.")
        if not self.url:
            raise ValueError("Pool URL must not be empty.")
        MAX_POOL_FEE_PCT = Decimal(100)
        if self.fee_pct < 0 or self.fee_pct > MAX_POOL_FEE_PCT:
            raise ValueError("Pool fee must be between 0 and 100.")
        if self.min_payout <= 0:
            raise ValueError("Minimum payout must be positive.")

    @classmethod
    def create(
        cls,
        *,
        name: str,
        url: str,
        fee_pct: str,
        payout_scheme: PoolPayoutScheme = PoolPayoutScheme.PPS,
        min_payout: str = "0.001",
    ) -> PoolConfig:
        return cls(
            pool_id=PoolAdapterId.generate(),
            name=name,
            url=url,
            fee_pct=Decimal(fee_pct),
            payout_scheme=payout_scheme,
            min_payout=Decimal(min_payout),
        )

    @property
    def fee_fraction(self) -> Decimal:
        """Fee as a fraction (fee_pct / 100)."""
        return self.fee_pct / Decimal(100)


# ── Pool Adapter Protocol (Deliverable 5, 10) ──


class PoolAdapterProtocol(Protocol):
    """Protocol for pool adapter implementations.

    Per Section 09.2: physical integration requires approved adapter,
    verified operator authority, safety limits, reliable telemetry,
    failure handling, and explicit authorization.

    Per AD-015: real pool integration requires explicit approval and
    safety controls. This protocol defines the interface; the actual
    pool connection is NOT activated without explicit authorization.
    """

    @property
    def pool_config(self) -> PoolConfig: ...

    @property
    def is_authorized(self) -> bool: ...

    def authorize(self, authorized_by: str) -> None: ...

    def submit_share(self, share_hash: str, equipment_id: MiningEquipmentId) -> bool: ...

    def get_pending_rewards(self) -> Decimal: ...

    def request_payout(self) -> bool: ...


# ── Simulated Pool Adapter (Deliverable 5) ──


class SimulatedPoolAdapter:
    """Simulated pool adapter for mining simulation.

    Per AD-015: simulation only — does NOT connect to a real pool.
    Per AD-023: deterministic simulation.

    The simulated pool tracks submitted shares and accumulates rewards
    deterministically based on the pool's payout scheme and fee.
    """

    def __init__(self, config: PoolConfig) -> None:
        self._config = config
        self._authorized = False
        self._authorized_by = ""
        self._shares: list[tuple[str, MiningEquipmentId]] = []
        self._pending_rewards = Decimal(0)
        self._total_paid = Decimal(0)

    @property
    def pool_config(self) -> PoolConfig:
        return self._config

    @property
    def is_authorized(self) -> bool:
        return self._authorized

    def authorize(self, authorized_by: str) -> None:
        """Authorize the pool adapter.

        Per AD-015: explicit authorization required for real pool integration.
        In simulation, this is a no-op that marks authorization.
        """
        if not authorized_by:
            raise ValueError("authorized_by must not be empty.")
        self._authorized = True
        self._authorized_by = authorized_by

    def submit_share(self, share_hash: str, equipment_id: MiningEquipmentId) -> bool:
        """Submit a share to the simulated pool.

        Returns True if the share was accepted.
        """
        if not share_hash:
            raise ValueError("share_hash must not be empty.")
        self._shares.append((share_hash, equipment_id))
        return True

    def add_rewards(self, amount: Decimal) -> None:
        """Add mining rewards to pending balance (called by simulator)."""
        if amount < 0:
            raise ValueError("Reward amount must be non-negative.")
        net_amount = amount * (Decimal(1) - self._config.fee_fraction)
        self._pending_rewards += net_amount

    def get_pending_rewards(self) -> Decimal:
        return self._pending_rewards

    def request_payout(self) -> bool:
        """Request a payout from the simulated pool."""
        if self._pending_rewards < self._config.min_payout:
            return False
        self._total_paid += self._pending_rewards
        self._pending_rewards = Decimal(0)
        return True

    @property
    def total_paid(self) -> Decimal:
        return self._total_paid

    @property
    def share_count(self) -> int:
        return len(self._shares)

    @property
    def is_simulation(self) -> bool:
        return True


# ── Hardware Telemetry (Deliverable 6) ──


@dataclass
class TelemetryReading:
    """Hardware telemetry reading per Section 09.2.

    Per Section 09.2: reliable telemetry.
    Per AD-022: structured audit records.

    Attributes:
        reading_id: Stable unique identifier.
        equipment_id: Equipment this reading is from.
        timestamp: UTC timestamp.
        temperature_c: Temperature in Celsius.
        hash_rate: Current hash rate.
        power_w: Current power draw in watts.
        fan_speed_rpm: Fan speed in RPM (if applicable).
        status: Hardware status.
    """

    reading_id: TelemetryId
    equipment_id: MiningEquipmentId
    timestamp: datetime
    temperature_c: Decimal
    hash_rate: HashRate
    power_w: Decimal
    fan_speed_rpm: Decimal = Decimal("0")
    status: MiningHardwareStatus = MiningHardwareStatus.RUNNING

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class TelemetryHistory:
    """History of telemetry readings for a piece of equipment.

    Per Section 09.2: reliable telemetry.
    Per AD-022: observability and audit.
    """

    equipment_id: MiningEquipmentId
    readings: list[TelemetryReading] = field(default_factory=list)

    def add(self, reading: TelemetryReading) -> None:
        """Add a telemetry reading."""
        if reading.equipment_id != self.equipment_id:
            raise ValueError("Telemetry reading equipment_id mismatch.")
        self.readings.append(reading)

    @property
    def count(self) -> int:
        return len(self.readings)

    @property
    def latest(self) -> TelemetryReading | None:
        if not self.readings:
            return None
        return self.readings[-1]

    @property
    def avg_temperature(self) -> Decimal:
        if not self.readings:
            return Decimal(0)
        total = sum((r.temperature_c for r in self.readings), Decimal(0))
        return total / Decimal(len(self.readings))

    @property
    def max_temperature(self) -> Decimal:
        if not self.readings:
            return Decimal(0)
        return max(r.temperature_c for r in self.readings)

    @property
    def avg_hash_rate(self) -> Decimal:
        """Average hash rate in H/s."""
        if not self.readings:
            return Decimal(0)
        total = sum((r.hash_rate.hash_per_second for r in self.readings), Decimal(0))
        return total / Decimal(len(self.readings))


# ── Temperature Policy (Deliverable 7) ──


@dataclass(frozen=True)
class TemperaturePolicy:
    """Temperature safety policy per Section 09.2.

    Per Section 09.2: safety limits, temperature policies.
    Per AD-013: enforce hard limits.

    Defines safe operating temperature ranges and actions for violations.
    Temperatures are in Celsius.

    Attributes:
        min_safe: Minimum safe operating temperature.
        max_safe: Maximum safe operating temperature.
        throttle_threshold: Temperature at which to start throttling.
        shutdown_threshold: Temperature at which to initiate shutdown.
        alert_threshold: Temperature at which to issue an alert.
    """

    min_safe: Decimal = Decimal("0")
    max_safe: Decimal = Decimal("80")
    throttle_threshold: Decimal = Decimal("75")
    shutdown_threshold: Decimal = Decimal("90")
    alert_threshold: Decimal = Decimal("70")

    def __post_init__(self) -> None:
        if self.min_safe >= self.max_safe:
            raise ValueError("Min safe temp must be below max safe temp.")
        if self.throttle_threshold > self.shutdown_threshold:
            raise ValueError("Throttle threshold must not exceed shutdown threshold.")
        if self.alert_threshold > self.throttle_threshold:
            raise ValueError("Alert threshold must not exceed throttle threshold.")

    def evaluate(self, temperature_c: Decimal) -> TemperatureAction:
        """Evaluate a temperature reading against the policy.

        Returns the action to take:
        - NONE if temperature is within safe range.
        - ALERT if temperature is at or above alert_threshold.
        - THROTTLE if temperature is at or above throttle_threshold.
        - SHUTDOWN if temperature is at or above shutdown_threshold.
        """
        if temperature_c >= self.shutdown_threshold:
            return TemperatureAction.SHUTDOWN
        if temperature_c >= self.throttle_threshold:
            return TemperatureAction.THROTTLE
        if temperature_c >= self.alert_threshold:
            return TemperatureAction.ALERT
        if temperature_c < self.min_safe:
            return TemperatureAction.ALERT
        return TemperatureAction.NONE

    def is_safe(self, temperature_c: Decimal) -> bool:
        """True if the temperature is within the safe operating range."""
        return self.min_safe <= temperature_c <= self.max_safe

    def is_violation(self, temperature_c: Decimal) -> bool:
        """True if the temperature violates the safe operating range."""
        return not self.is_safe(temperature_c)

    @classmethod
    def from_equipment(cls, equipment: EquipmentSpec) -> TemperaturePolicy:
        """Create a temperature policy from equipment specs."""
        return cls(
            min_safe=equipment.min_operating_temp_c,
            max_safe=equipment.max_operating_temp_c,
            throttle_threshold=equipment.throttle_temp_c,
            shutdown_threshold=equipment.shutdown_temp_c,
            alert_threshold=(equipment.throttle_temp_c + equipment.min_operating_temp_c)
            / Decimal(2),
        )


# ── Failure Simulation (Deliverable 9) ──


@dataclass
class FailureEvent:
    """A simulated or real hardware failure event.

    Per Section 09.2: failure handling.
    Per AD-023: fault injection and deterministic simulation.

    Attributes:
        event_id: Stable unique identifier.
        equipment_id: Equipment that failed.
        failure_type: Type of failure.
        start_time: When the failure started (UTC).
        end_time: When the failure was resolved (UTC, None if ongoing).
        description: Human-readable description.
    """

    event_id: FailureEventId
    equipment_id: MiningEquipmentId
    failure_type: FailureType
    start_time: datetime
    end_time: datetime | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is None:
            raise ValueError("start_time must be timezone-aware (UTC).")
        if self.end_time is not None and self.end_time.tzinfo is None:
            raise ValueError("end_time must be timezone-aware (UTC).")
        if self.end_time is not None and self.end_time < self.start_time:
            raise ValueError("end_time must not be before start_time.")

    @property
    def is_resolved(self) -> bool:
        return self.end_time is not None

    @property
    def duration(self) -> timedelta:
        """Duration of the failure (from start to end, or from start to now)."""
        end = self.end_time or datetime.now(UTC)
        return end - self.start_time

    @property
    def duration_seconds(self) -> Decimal:
        """Duration in seconds as a Decimal."""
        return Decimal(self.duration.total_seconds())

    @classmethod
    def create(
        cls,
        *,
        equipment_id: MiningEquipmentId,
        failure_type: FailureType,
        start_time: datetime,
        description: str = "",
    ) -> FailureEvent:
        return cls(
            event_id=FailureEventId.generate(),
            equipment_id=equipment_id,
            failure_type=failure_type,
            start_time=start_time,
            description=description,
        )

    def resolve(self, end_time: datetime | None = None) -> FailureEvent:
        """Return a new FailureEvent with the end time set."""
        if self.is_resolved:
            raise ValueError("Failure event is already resolved.")
        resolved_at = end_time or datetime.now(UTC)
        return FailureEvent(
            event_id=self.event_id,
            equipment_id=self.equipment_id,
            failure_type=self.failure_type,
            start_time=self.start_time,
            end_time=resolved_at,
            description=self.description,
        )


# ── Mining Session Configuration ──


@dataclass(frozen=True)
class MiningSessionConfig:
    """Configuration for a mining simulation session.

    Combines equipment, pool, electricity, and depreciation into a single
    deterministic configuration for the simulator.

    Per AD-023: deterministic simulation — same config produces same results.
    """

    session_id: MiningSessionId
    equipment: EquipmentSpec
    pool: PoolConfig
    electricity: ElectricityConfig
    depreciation: DepreciationConfig
    temperature_policy: TemperaturePolicy
    network_difficulty: NetworkDifficulty
    block_reward: BlockReward
    btc_price: Decimal
    uptime_pct: Decimal = Decimal("95")

    def __post_init__(self) -> None:
        if self.btc_price <= 0:
            raise ValueError("BTC price must be positive.")
        MAX_PCT = Decimal(100)
        if self.uptime_pct < 0 or self.uptime_pct > MAX_PCT:
            raise ValueError("Uptime percentage must be between 0 and 100.")

    @classmethod
    def create(  # noqa: PLR0913
        cls,
        *,
        equipment: EquipmentSpec,
        pool: PoolConfig,
        electricity: ElectricityConfig,
        network_difficulty: NetworkDifficulty,
        block_reward: BlockReward,
        btc_price: str,
        uptime_pct: str = "95",
        temperature_policy: TemperaturePolicy | None = None,
    ) -> MiningSessionConfig:
        dep = DepreciationConfig.from_equipment(equipment)
        temp_pol = temperature_policy or TemperaturePolicy.from_equipment(equipment)
        return cls(
            session_id=MiningSessionId.generate(),
            equipment=equipment,
            pool=pool,
            electricity=electricity,
            depreciation=dep,
            temperature_policy=temp_pol,
            network_difficulty=network_difficulty,
            block_reward=block_reward,
            btc_price=Decimal(btc_price),
            uptime_pct=Decimal(uptime_pct),
        )


# ── Mining Simulation Result (Deliverable 1) ──


@dataclass
class MiningSimulationResult:
    """Result of a mining simulation run.

    Per Section 09.1: net profitability and uncertainty.
    Per AD-023: deterministic simulation with repeatable verification.

    Attributes:
        session_id: Mining session identifier.
        daily_gross_revenue_btc: Gross daily revenue before pool fees.
        daily_pool_fee_btc: Daily pool fee in BTC.
        daily_net_revenue_btc: Net daily revenue after pool fees.
        daily_electricity_cost: Daily electricity cost in fiat.
        daily_depreciation: Daily depreciation cost in fiat.
        daily_net_profit: Net daily profit (revenue - electricity - depreciation) in fiat.
        is_profitable: True if daily_net_profit > 0.
        break_even_btc_price: BTC price at which daily_net_profit = 0.
        daily_btc_mined: Estimated BTC mined per day.
        efficiency_j_per_th: Equipment energy efficiency.
        uncertainty_range: Profitability uncertainty range (high/low estimate).
        is_simulation: Always True (simulation only, not real hardware).
    """

    session_id: MiningSessionId
    daily_gross_revenue_btc: Decimal
    daily_pool_fee_btc: Decimal
    daily_net_revenue_btc: Decimal
    daily_electricity_cost: Decimal
    daily_depreciation: Decimal
    daily_net_profit: Decimal
    is_profitable: bool
    break_even_btc_price: Decimal
    daily_btc_mined: Decimal
    efficiency_j_per_th: Decimal
    uncertainty_range: tuple[Decimal, Decimal]
    is_simulation: bool = True

    @property
    def daily_revenue_fiat(self) -> Decimal:
        """Daily net revenue in fiat currency."""
        return self.daily_net_revenue_btc * self.break_even_btc_price

    @property
    def uncertainty_low(self) -> Decimal:
        return self.uncertainty_range[0]

    @property
    def uncertainty_high(self) -> Decimal:
        return self.uncertainty_range[1]


# ── Mining Financial Entry (Deliverable 8) ──


@dataclass
class MiningFinancialEntry:
    """Mining financial entry for ledger integration.

    Per Section 09.2: mining financial records must remain distinguishable
    from trading records.

    Attributes:
        session_id: Mining session identifier.
        revenue_btc: Mining revenue in BTC.
        electricity_cost: Electricity cost in fiat.
        depreciation_cost: Depreciation cost in fiat.
        pool_fee_btc: Pool fee in BTC.
        net_profit_fiat: Net profit in fiat.
        timestamp: UTC timestamp.
        entry_type: Type of mining financial entry.
    """

    session_id: MiningSessionId
    revenue_btc: Decimal
    electricity_cost: Decimal
    depreciation_cost: Decimal
    pool_fee_btc: Decimal
    net_profit_fiat: Decimal
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    entry_type: str = "mining_revenue"

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")

    @property
    def is_mining(self) -> bool:
        """Always True — distinguishes mining entries from trading entries."""
        return True

    @classmethod
    def from_result(
        cls,
        result: MiningSimulationResult,
        btc_price: Decimal,
    ) -> MiningFinancialEntry:
        """Create a financial entry from a simulation result."""
        return cls(
            session_id=result.session_id,
            revenue_btc=result.daily_net_revenue_btc,
            electricity_cost=result.daily_electricity_cost,
            depreciation_cost=result.daily_depreciation,
            pool_fee_btc=result.daily_pool_fee_btc,
            net_profit_fiat=result.daily_net_profit,
            entry_type="mining_daily_revenue",
        )


# ── Controlled Hardware Adapter (Deliverable 10) ──


@dataclass(frozen=True)
class HardwareAuthorization:
    """Authorization for physical hardware operations.

    Per AD-015: real hardware and pool integration require explicit approval
    and safety controls.
    Per Section 09.2: verified operator authority; explicit authorization.

    Attributes:
        authorized: Whether physical operations are authorized.
        authorized_by: Identity of the authorizing operator.
        authorized_at: UTC timestamp of authorization.
        expires_at: UTC expiry timestamp (None = no expiry).
        scope: Scope of authorization (e.g., "telemetry_only", "full_operation").
    """

    authorized: bool
    authorized_by: str
    authorized_at: datetime
    expires_at: datetime | None = None
    scope: str = "telemetry_only"

    def __post_init__(self) -> None:
        if self.authorized_at.tzinfo is None:
            raise ValueError("authorized_at must be timezone-aware (UTC).")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware (UTC).")

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    @property
    def is_active(self) -> bool:
        return self.authorized and not self.is_expired


class HardwareAdapterProtocol(Protocol):
    """Protocol for hardware adapter implementations.

    Per Section 09.2: physical integration requires approved adapter,
    verified operator authority, safety limits, reliable telemetry,
    failure handling, and explicit authorization.

    Per AD-015: real hardware integration requires explicit approval and
    safety controls. This protocol defines the interface; the actual
    hardware is NOT activated without explicit authorization.

    The MacBook is a control interface, not the assumed mining hardware
    (Section 09.2).
    """

    @property
    def adapter_id(self) -> HardwareAdapterId: ...

    @property
    def equipment_id(self) -> MiningEquipmentId: ...

    @property
    def is_authorized(self) -> bool: ...

    def authorize(self, authorization: HardwareAuthorization) -> None: ...

    def read_telemetry(self) -> TelemetryReading: ...

    def start_mining(self) -> bool: ...

    def stop_mining(self) -> bool: ...

    def emergency_stop(self) -> bool: ...


# ── Mining Safety State (Deliverable 7, 10) ──


@dataclass
class MiningSafetyState:
    """Safety state for mining operations.

    Per AD-013: enforce hard limits.
    Per Section 09.2: safety limits, failure handling.
    Per AD-015: physical operations remain separately authorized.

    Attributes:
        emergency_stop_active: True if emergency stop has been triggered.
        physical_operations_authorized: True if physical mining is authorized.
        last_temperature_c: Last recorded temperature.
        last_telemetry: Last telemetry reading (None if none).
        active_failures: List of currently active failure events.
    """

    emergency_stop_active: bool = False
    physical_operations_authorized: bool = False
    last_temperature_c: Decimal | None = None
    last_telemetry: TelemetryReading | None = None
    active_failures: list[FailureEvent] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        """True if no emergency stop is active and no critical failures."""
        return not (
            self.emergency_stop_active
            or any(f.failure_type == FailureType.OVERHEAT for f in self.active_failures)
        )

    def trigger_emergency_stop(self) -> None:
        """Trigger emergency stop.

        Per AD-013: emergency stop must block new operations.
        Per Section 09.2: safety limits.
        """
        self.emergency_stop_active = True

    def clear_emergency_stop(self, authorized_by: str) -> None:
        """Clear emergency stop (requires explicit authorization).

        Per AD-015: explicit authorization for physical operations.
        """
        if not authorized_by:
            raise ValueError("authorized_by must not be empty.")
        self.emergency_stop_active = False

    def authorize_physical_operations(self, authorized_by: str) -> None:
        """Authorize physical mining operations.

        Per AD-015: real hardware requires explicit approval.
        Per Section 09.2: verified operator authority.
        """
        if not authorized_by:
            raise ValueError("authorized_by must not be empty.")
        if self.emergency_stop_active:
            raise PermissionError(
                "Cannot authorize physical operations while emergency stop is active."
            )
        self.physical_operations_authorized = True

    def revoke_physical_operations(self) -> None:
        """Revoke physical mining operations authorization."""
        self.physical_operations_authorized = False

    def add_failure(self, event: FailureEvent) -> None:
        """Record an active failure event."""
        self.active_failures.append(event)

    def resolve_failure(self, event_id: FailureEventId) -> FailureEvent | None:
        """Resolve a failure event by ID. Returns the resolved event or None."""
        for i, event in enumerate(self.active_failures):
            if event.event_id == event_id:
                resolved = event.resolve()
                self.active_failures[i] = resolved
                return resolved
        return None

    @property
    def failure_count(self) -> int:
        return len(self.active_failures)


# ── Mining Safety Limits (Deliverable 10) ──


@dataclass(frozen=True)
class MiningSafetyLimits:
    """Safety limits for mining hardware operations.

    Per Section 09.2: safety limits.
    Per AD-013: enforce hard limits.

    Attributes:
        max_temperature_c: Maximum safe operating temperature.
        max_power_w: Maximum power draw.
        min_hash_rate: Minimum acceptable hash rate (H/s).
        max_downtime_pct: Maximum acceptable downtime percentage.
    """

    max_temperature_c: Decimal = Decimal("90")
    max_power_w: Decimal = Decimal("5000")
    min_hash_rate: Decimal = Decimal("0")
    max_downtime_pct: Decimal = Decimal("20")

    def __post_init__(self) -> None:
        if self.max_temperature_c <= 0:
            raise ValueError("Max temperature must be positive.")
        if self.max_power_w <= 0:
            raise ValueError("Max power must be positive.")
        MAX_DOWNTIME_PCT = Decimal(100)
        if self.max_downtime_pct < 0 or self.max_downtime_pct > MAX_DOWNTIME_PCT:
            raise ValueError("Max downtime must be between 0 and 100.")

    def check_temperature(self, temperature_c: Decimal) -> bool:
        """True if temperature is within safe limits."""
        return temperature_c <= self.max_temperature_c

    def check_power(self, power_w: Decimal) -> bool:
        """True if power is within safe limits."""
        return power_w <= self.max_power_w

    def check_hash_rate(self, hash_rate: Decimal) -> bool:
        """True if hash rate is above minimum."""
        return hash_rate >= self.min_hash_rate

    def check_all(
        self,
        temperature_c: Decimal,
        power_w: Decimal,
        hash_rate: Decimal,
        downtime_pct: Decimal,
    ) -> bool:
        """Check all safety limits."""
        return (
            self.check_temperature(temperature_c)
            and self.check_power(power_w)
            and self.check_hash_rate(hash_rate)
            and downtime_pct <= self.max_downtime_pct
        )
