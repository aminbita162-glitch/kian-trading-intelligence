"""Risk policy and authorization contracts for Kian Trading Intelligence.

Per AD-004 (Four Agents + Independent Safety Kernel): the Risk Kernel is a
deterministic safety service, not an agent. It validates tenant and profile
authorization; session state; venue and instrument eligibility; capital and
exposure; daily loss and drawdown; concentration and correlation; liquidity
and volatility; market-data freshness; emergency-stop state; risk policy
version; order-specific authorization validity.

Invariant: No exposure-increasing order may reach an exchange adapter without
valid risk authorization.

Per AD-013 (Dynamic Risk Management): enforce hard limits for exposure, daily
loss, drawdown, concentration, volatility, liquidity, and correlated positions.

Per AD-014 (Deterministic Execution): use durable order state, unique
identifiers, idempotency, explicit partial-fill handling, and reconciliation.

Per Section 05.4 (Risk Reservation and Concurrency): concurrent strategies and
sessions must not spend the same risk budget. Risk reservations must be
concurrency-safe and tied to specific order parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4


class RiskPolicyStatus(StrEnum):
    """Status of a risk policy version."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class AuthorizationStatus(StrEnum):
    """Status of a risk authorization."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"


class ReservationStatus(StrEnum):
    """Status of a risk capacity reservation."""

    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    CONSUMED = "consumed"


@dataclass(frozen=True)
class RiskPolicyId:
    """Stable identity for a risk policy."""

    value: UUID

    @classmethod
    def generate(cls) -> RiskPolicyId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class RiskAuthorizationId:
    """Stable identity for a risk authorization.

    Per Section 05.3: every trade intent, order submission, fill, and financial
    posting must have a stable identity.
    """

    value: UUID

    @classmethod
    def generate(cls) -> RiskAuthorizationId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ReservationId:
    """Stable identity for a risk capacity reservation."""

    value: UUID

    @classmethod
    def generate(cls) -> ReservationId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class RiskPolicy:
    """Versioned risk policy per AD-013 and Section 05.4.

    A risk policy defines hard limits that the Risk Kernel enforces
    deterministically. Each policy has a version that is tracked and
    cannot be silently changed.

    Attributes:
        policy_id: Stable unique identifier.
        tenant_id: Tenant scope.
        version: Monotonically increasing version number.
        status: Policy lifecycle status.
        max_position_value: Maximum total exposure value (quote currency).
        max_daily_loss: Maximum daily loss before trading stops.
        max_drawdown: Maximum drawdown from peak.
        max_concentration_pct: Maximum concentration as percentage (0-100).
        max_position_per_symbol: Maximum number of open positions per symbol.
        min_liquidity_usd: Minimum liquidity required for a symbol.
        max_volatility: Maximum acceptable volatility for a symbol.
        created_at: UTC creation timestamp.
        activated_at: UTC activation timestamp (None if not yet active).
    """

    policy_id: RiskPolicyId
    tenant_id: str
    version: int
    status: RiskPolicyStatus = RiskPolicyStatus.DRAFT
    max_position_value: str = "100000.00"
    max_daily_loss: str = "5000.00"
    max_drawdown: str = "10000.00"
    max_concentration_pct: str = "25.0"
    max_position_per_symbol: int = 10
    min_liquidity_usd: str = "10000.00"
    max_volatility: str = "0.05"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("Version must be >= 1.")
        if float(self.max_position_value) <= 0:
            raise ValueError("max_position_value must be positive.")
        if float(self.max_daily_loss) <= 0:
            raise ValueError("max_daily_loss must be positive.")
        if float(self.max_drawdown) <= 0:
            raise ValueError("max_drawdown must be positive.")
        conc = float(self.max_concentration_pct)
        CONC_MIN = 0.0
        CONC_MAX = 100.0
        if not CONC_MIN < conc <= CONC_MAX:
            raise ValueError("max_concentration_pct must be in (0, 100].")
        if self.max_position_per_symbol < 1:
            raise ValueError("max_position_per_symbol must be >= 1.")
        if float(self.min_liquidity_usd) < 0:
            raise ValueError("min_liquidity_usd must be non-negative.")
        if float(self.max_volatility) < 0:
            raise ValueError("max_volatility must be non-negative.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    def activate(self) -> RiskPolicy:
        """Activate this policy, transitioning DRAFT -> ACTIVE.

        Returns a new activated copy; the original remains immutable.
        """
        if self.status is not RiskPolicyStatus.DRAFT:
            raise ValueError(f"Cannot activate policy in status {self.status}.")
        return RiskPolicy(
            policy_id=self.policy_id,
            tenant_id=self.tenant_id,
            version=self.version,
            status=RiskPolicyStatus.ACTIVE,
            max_position_value=self.max_position_value,
            max_daily_loss=self.max_daily_loss,
            max_drawdown=self.max_drawdown,
            max_concentration_pct=self.max_concentration_pct,
            max_position_per_symbol=self.max_position_per_symbol,
            min_liquidity_usd=self.min_liquidity_usd,
            max_volatility=self.max_volatility,
            created_at=self.created_at,
            activated_at=datetime.now(UTC),
        )

    def supersede(self) -> RiskPolicy:
        """Mark this policy as superseded by a newer version."""
        if self.status is not RiskPolicyStatus.ACTIVE:
            raise ValueError(f"Cannot supersede policy in status {self.status}.")
        return RiskPolicy(
            policy_id=self.policy_id,
            tenant_id=self.tenant_id,
            version=self.version,
            status=RiskPolicyStatus.SUPERSEDED,
            max_position_value=self.max_position_value,
            max_daily_loss=self.max_daily_loss,
            max_drawdown=self.max_drawdown,
            max_concentration_pct=self.max_concentration_pct,
            max_position_per_symbol=self.max_position_per_symbol,
            min_liquidity_usd=self.min_liquidity_usd,
            max_volatility=self.max_volatility,
            created_at=self.created_at,
            activated_at=self.activated_at,
        )

    @classmethod
    def create(  # noqa: PLR0913
        cls,
        *,
        tenant_id: str,
        version: int = 1,
        max_position_value: str = "100000.00",
        max_daily_loss: str = "5000.00",
        max_drawdown: str = "10000.00",
        max_concentration_pct: str = "25.0",
        max_position_per_symbol: int = 10,
        min_liquidity_usd: str = "10000.00",
        max_volatility: str = "0.05",
    ) -> RiskPolicy:
        """Create a new DRAFT risk policy."""
        return cls(
            policy_id=RiskPolicyId.generate(),
            tenant_id=tenant_id,
            version=version,
            status=RiskPolicyStatus.DRAFT,
            max_position_value=max_position_value,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            max_concentration_pct=max_concentration_pct,
            max_position_per_symbol=max_position_per_symbol,
            min_liquidity_usd=min_liquidity_usd,
            max_volatility=max_volatility,
        )


@dataclass
class RiskAuthorization:
    """Authorization issued by the Risk Kernel for a specific order.

    Per Section 05.4: expired or materially changed authorizations must be
    rejected. The authorization is tied to specific order parameters.

    Attributes:
        authorization_id: Stable unique identifier.
        tenant_id: Tenant scope.
        policy_id: Policy under which authorization was granted.
        policy_version: Version of the policy at authorization time.
        intent_id: Order intent this authorization covers.
        symbol: Trading symbol.
        side: Order side ("buy" or "sell").
        quantity: Authorized quantity.
        max_price: Maximum price for buy orders (None = no limit).
        status: Authorization status.
        created_at: UTC creation timestamp.
        expires_at: UTC expiry timestamp.
        consumed_at: UTC consumption timestamp (None if not consumed).
        reason: Denial reason if status is DENIED.
    """

    authorization_id: RiskAuthorizationId
    tenant_id: str
    policy_id: RiskPolicyId
    policy_version: int
    intent_id: str
    symbol: str
    side: str
    quantity: str
    max_price: str | None = None
    status: AuthorizationStatus = AuthorizationStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(seconds=30))
    consumed_at: datetime | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {self.side!r}. Must be 'buy' or 'sell'.")
        if float(self.quantity) <= 0:
            raise ValueError("Quantity must be positive.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware (UTC).")

    @property
    def is_expired(self) -> bool:
        """True if the authorization has expired."""
        return datetime.now(UTC) >= self.expires_at

    @property
    def is_valid(self) -> bool:
        """True if the authorization is valid for use (APPROVED and not expired)."""
        return self.status is AuthorizationStatus.APPROVED and not self.is_expired

    @property
    def is_exposure_increasing(self) -> bool:
        """True if this authorization increases exposure (buy orders)."""
        return self.side == "buy"

    def consume(self) -> RiskAuthorization:
        """Mark the authorization as consumed.

        Per Section 05.3: idempotency — a consumed authorization cannot
        be reused.
        """
        if self.status is not AuthorizationStatus.APPROVED:
            raise ValueError(f"Cannot consume authorization in status {self.status}.")
        if self.is_expired:
            raise ValueError("Cannot consume expired authorization.")
        return RiskAuthorization(
            authorization_id=self.authorization_id,
            tenant_id=self.tenant_id,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            intent_id=self.intent_id,
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            max_price=self.max_price,
            status=AuthorizationStatus.CONSUMED,
            created_at=self.created_at,
            expires_at=self.expires_at,
            consumed_at=datetime.now(UTC),
            reason=self.reason,
        )

    def cancel(self, reason: str = "") -> RiskAuthorization:
        """Cancel the authorization."""
        return RiskAuthorization(
            authorization_id=self.authorization_id,
            tenant_id=self.tenant_id,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            intent_id=self.intent_id,
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            max_price=self.max_price,
            status=AuthorizationStatus.CANCELLED,
            created_at=self.created_at,
            expires_at=self.expires_at,
            consumed_at=self.consumed_at,
            reason=reason or "Cancelled",
        )


@dataclass
class RiskReservation:
    """Concurrency-safe risk capacity reservation.

    Per Section 05.4: concurrent strategies and sessions must not spend the
    same risk budget. Risk reservations must be concurrency-safe and tied to
    specific order parameters. Expired or materially changed authorizations
    must be rejected.

    Attributes:
        reservation_id: Stable unique identifier.
        tenant_id: Tenant scope.
        authorization_id: Linked risk authorization.
        intent_id: Order intent this reservation covers.
        reserved_value: Value reserved from the risk budget.
        status: Reservation status.
        created_at: UTC creation timestamp.
        expires_at: UTC expiry timestamp.
        released_at: UTC release timestamp (None if still active).
    """

    reservation_id: ReservationId
    tenant_id: str
    authorization_id: RiskAuthorizationId
    intent_id: str
    reserved_value: str
    status: ReservationStatus = ReservationStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(seconds=60))
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        if float(self.reserved_value) <= 0:
            raise ValueError("reserved_value must be positive.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware (UTC).")

    @property
    def is_expired(self) -> bool:
        """True if the reservation has expired."""
        return datetime.now(UTC) >= self.expires_at

    @property
    def is_active(self) -> bool:
        """True if the reservation is active and not expired."""
        return self.status is ReservationStatus.ACTIVE and not self.is_expired

    def release(self) -> RiskReservation:
        """Release the reservation back to the risk budget."""
        return RiskReservation(
            reservation_id=self.reservation_id,
            tenant_id=self.tenant_id,
            authorization_id=self.authorization_id,
            intent_id=self.intent_id,
            reserved_value=self.reserved_value,
            status=ReservationStatus.RELEASED,
            created_at=self.created_at,
            expires_at=self.expires_at,
            released_at=datetime.now(UTC),
        )

    def consume(self) -> RiskReservation:
        """Consume the reservation (order was filled)."""
        return RiskReservation(
            reservation_id=self.reservation_id,
            tenant_id=self.tenant_id,
            authorization_id=self.authorization_id,
            intent_id=self.intent_id,
            reserved_value=self.reserved_value,
            status=ReservationStatus.CONSUMED,
            created_at=self.created_at,
            expires_at=self.expires_at,
            released_at=datetime.now(UTC),
        )


@dataclass
class RiskAssessment:
    """Result of a risk assessment by the Risk Kernel.

    The kernel evaluates an order intent against the active risk policy and
    current exposure state. The assessment is deterministic: same inputs
    always produce the same decision.

    Attributes:
        authorized: Whether the order is authorized.
        reason: Human-readable reason for the decision.
        checked_limits: List of limits that were checked.
        policy_id: Policy under which the assessment was made.
        policy_version: Version of the policy.
        assessed_at: UTC assessment timestamp.
    """

    authorized: bool
    reason: str
    checked_limits: list[str] = field(default_factory=list)
    policy_id: RiskPolicyId | None = None
    policy_version: int = 0
    assessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ── Legal Session State Transitions ──
# Maps each session state to the set of states it may legally transition to.
# Per Section 06.2: session states and their transitions.
LEGAL_SESSION_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"scheduled", "cancelled"},
    "scheduled": {"preflight", "cancelled"},
    "preflight": {"awaiting_user_approval", "cancelled", "safe_halt"},
    "awaiting_user_approval": {"running", "cancelled", "safe_halt"},
    "running": {"degraded", "safe_halt", "reconciling", "completed"},
    "degraded": {"running", "safe_halt", "reconciling", "completed"},
    "safe_halt": {"reconciling"},
    "reconciling": {"running", "completed", "safe_halt"},
    "completed": set(),
    "cancelled": set(),
}
