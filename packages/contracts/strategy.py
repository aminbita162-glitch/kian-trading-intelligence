"""Strategy versioning contracts for Kian Trading Intelligence.

Per deliverable 4: strategy versioning — every strategy must be versioned
with immutable parameters. A new version creates a new immutable snapshot;
the old version is preserved for reproducibility.

Per AD-012 (Strategy Validation Pipeline): require historical testing,
out-of-sample analysis, walk-forward validation, and paper trading.

Per Section 08.4: no strategy may be represented as guaranteed profitable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class StrategyStatus(StrEnum):
    """Lifecycle status of a strategy version."""

    DRAFT = "draft"
    BACKTESTING = "backtesting"
    OUT_OF_SAMPLE = "out_of_sample"
    WALK_FORWARD = "walk_forward"
    PAPER_TRADING = "paper_trading"
    VALIDATED = "validated"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


# Legal status transitions for the strategy validation pipeline (Section 08.4).
LEGAL_STRATEGY_TRANSITIONS: dict[StrategyStatus, frozenset[StrategyStatus]] = {
    StrategyStatus.DRAFT: frozenset(
        {
            StrategyStatus.BACKTESTING,
            StrategyStatus.REJECTED,
        }
    ),
    StrategyStatus.BACKTESTING: frozenset(
        {
            StrategyStatus.OUT_OF_SAMPLE,
            StrategyStatus.REJECTED,
        }
    ),
    StrategyStatus.OUT_OF_SAMPLE: frozenset(
        {
            StrategyStatus.WALK_FORWARD,
            StrategyStatus.REJECTED,
        }
    ),
    StrategyStatus.WALK_FORWARD: frozenset(
        {
            StrategyStatus.PAPER_TRADING,
            StrategyStatus.REJECTED,
        }
    ),
    StrategyStatus.PAPER_TRADING: frozenset(
        {
            StrategyStatus.VALIDATED,
            StrategyStatus.REJECTED,
        }
    ),
    StrategyStatus.VALIDATED: frozenset(
        {
            StrategyStatus.ACTIVE,
            StrategyStatus.REJECTED,
        }
    ),
    StrategyStatus.ACTIVE: frozenset(
        {
            StrategyStatus.SUPERSEDED,
        }
    ),
    StrategyStatus.SUPERSEDED: frozenset(),
    StrategyStatus.REJECTED: frozenset(),
}


@dataclass(frozen=True)
class StrategyId:
    """Stable identity for a strategy (not its version)."""

    value: UUID

    @classmethod
    def generate(cls) -> StrategyId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class StrategyVersionId:
    """Stable identity for a specific version of a strategy."""

    value: UUID

    @classmethod
    def generate(cls) -> StrategyVersionId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class StrategyParameters:
    """Immutable parameters for a strategy version.

    Per deliverable 4: strategy versioning. Parameters are frozen so
    backtesting results are reproducible — same version + same data =
    same result.
    """

    symbol: str
    side: str
    quantity: str
    entry_signal: str
    exit_signal: str
    stop_loss_pct: str = "0.0"
    take_profit_pct: str = "0.0"
    max_position_value: str = "100000.00"

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side!r}.")
        if float(self.quantity) <= 0:
            raise ValueError("quantity must be positive.")
        if float(self.stop_loss_pct) < 0:
            raise ValueError("stop_loss_pct must be non-negative.")
        if float(self.take_profit_pct) < 0:
            raise ValueError("take_profit_pct must be non-negative.")
        if float(self.max_position_value) <= 0:
            raise ValueError("max_position_value must be positive.")


@dataclass
class StrategyVersion:
    """A versioned strategy with immutable parameters.

    Per deliverable 4: strategy versioning. Each version is an immutable
    snapshot of the strategy definition at a point in time.

    Attributes:
        version_id: Stable unique identifier.
        strategy_id: Parent strategy identifier.
        tenant_id: Tenant scope.
        version: Monotonically increasing version number.
        name: Human-readable strategy name.
        status: Current lifecycle status.
        parameters: Immutable strategy parameters.
        created_at: UTC creation timestamp.
        activated_at: UTC activation timestamp (None if not yet active).
    """

    version_id: StrategyVersionId
    strategy_id: StrategyId
    tenant_id: str
    version: int
    name: str
    status: StrategyStatus = StrategyStatus.DRAFT
    parameters: StrategyParameters | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("Version must be >= 1.")
        if not self.name:
            raise ValueError("name must not be empty.")
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if self.activated_at is not None and self.activated_at.tzinfo is None:
            raise ValueError("activated_at must be timezone-aware (UTC).")

    def can_transition(self, target: StrategyStatus) -> bool:
        return target in LEGAL_STRATEGY_TRANSITIONS.get(self.status, frozenset())

    def transition_to(self, target: StrategyStatus) -> StrategyVersion:
        if not self.can_transition(target):
            raise ValueError(f"Illegal strategy transition: {self.status.value} -> {target.value}")
        activated_at = self.activated_at
        if target is StrategyStatus.ACTIVE and activated_at is None:
            activated_at = datetime.now(UTC)
        return StrategyVersion(
            version_id=self.version_id,
            strategy_id=self.strategy_id,
            tenant_id=self.tenant_id,
            version=self.version,
            name=self.name,
            status=target,
            parameters=self.parameters,
            created_at=self.created_at,
            activated_at=activated_at,
        )

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        name: str,
        parameters: StrategyParameters,
        strategy_id: StrategyId | None = None,
        version: int = 1,
    ) -> StrategyVersion:
        return cls(
            version_id=StrategyVersionId.generate(),
            strategy_id=strategy_id or StrategyId.generate(),
            tenant_id=tenant_id,
            version=version,
            name=name,
            status=StrategyStatus.DRAFT,
            parameters=parameters,
        )
