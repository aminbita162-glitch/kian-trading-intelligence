"""Trading session state machine contracts for Kian Trading Intelligence.

Per Section 06.1: support recurring and one-time sessions with explicit
timezone handling. Every session must specify tenant and profile; strategy
version; exchange and instruments; capital allocation; risk policy; start
and stop conditions; preflight requirements; end-of-session position policy.

Per Section 06.2: session states DRAFT; SCHEDULED; PREFLIGHT;
AWAITING_USER_APPROVAL; RUNNING; DEGRADED; SAFE_HALT; RECONCILING;
COMPLETED; CANCELLED.

Per Section 06.3: scheduled events must not bypass authorization,
compliance, or risk checks. Critical failures require reconciliation and
human approval before resumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from contracts.enums import SessionState


@dataclass(frozen=True)
class SessionId:
    """Stable identity for a trading session."""

    value: UUID

    @classmethod
    def generate(cls) -> SessionId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


# ── Legal Session State Transitions ──
# Per Section 06.2: all legal transitions must be defined and tested.
LEGAL_SESSION_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.DRAFT: {
        SessionState.SCHEDULED,
        SessionState.CANCELLED,
    },
    SessionState.SCHEDULED: {
        SessionState.PREFLIGHT,
        SessionState.CANCELLED,
    },
    SessionState.PREFLIGHT: {
        SessionState.AWAITING_USER_APPROVAL,
        SessionState.CANCELLED,
        SessionState.SAFE_HALT,
    },
    SessionState.AWAITING_USER_APPROVAL: {
        SessionState.RUNNING,
        SessionState.CANCELLED,
        SessionState.SAFE_HALT,
    },
    SessionState.RUNNING: {
        SessionState.DEGRADED,
        SessionState.SAFE_HALT,
        SessionState.RECONCILING,
        SessionState.COMPLETED,
    },
    SessionState.DEGRADED: {
        SessionState.RUNNING,
        SessionState.SAFE_HALT,
        SessionState.RECONCILING,
        SessionState.COMPLETED,
    },
    SessionState.SAFE_HALT: {
        SessionState.RECONCILING,
    },
    SessionState.RECONCILING: {
        SessionState.RUNNING,
        SessionState.COMPLETED,
        SessionState.SAFE_HALT,
    },
    SessionState.COMPLETED: set(),  # terminal
    SessionState.CANCELLED: set(),  # terminal
}


@dataclass
class TradingSession:
    """Trading session per Section 06.

    A session coordinates a trading run: preflight checks, user approval,
    order execution, and graceful shutdown. Critical failures trigger
    SAFE_HALT and require reconciliation before resumption.

    Attributes:
        session_id: Stable unique identifier.
        tenant_id: Tenant scope.
        profile_id: Trading profile.
        strategy_version: Strategy version identifier.
        exchange: Exchange identifier.
        instruments: List of trading instruments.
        capital_allocation: Allocated capital.
        risk_policy_id: Active risk policy identifier.
        state: Current session state.
        created_at: UTC creation timestamp.
        started_at: UTC start timestamp (None if not started).
        stopped_at: UTC stop timestamp (None if not stopped).
        error_detail: Error description if degraded or halted.
    """

    session_id: SessionId
    tenant_id: str
    profile_id: str
    strategy_version: str
    exchange: str
    instruments: list[str]
    capital_allocation: str
    risk_policy_id: str
    state: SessionState = SessionState.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    error_detail: str = ""

    def __post_init__(self) -> None:
        if float(self.capital_allocation) <= 0:
            raise ValueError("capital_allocation must be positive.")
        if not self.instruments:
            raise ValueError("instruments must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    @classmethod
    def create(  # noqa: PLR0913
        cls,
        *,
        tenant_id: str,
        profile_id: str,
        strategy_version: str,
        exchange: str,
        instruments: list[str],
        capital_allocation: str,
        risk_policy_id: str,
    ) -> TradingSession:
        """Create a new session in the DRAFT state."""
        return cls(
            session_id=SessionId.generate(),
            tenant_id=tenant_id,
            profile_id=profile_id,
            strategy_version=strategy_version,
            exchange=exchange,
            instruments=list(instruments),
            capital_allocation=capital_allocation,
            risk_policy_id=risk_policy_id,
            state=SessionState.DRAFT,
        )

    def _can_transition(self, target: SessionState) -> bool:
        """Check if a state transition is legal."""
        return target in LEGAL_SESSION_TRANSITIONS.get(self.state, set())

    def transition_to(self, target: SessionState) -> TradingSession:
        """Transition to a new state, returning a new session instance.

        Raises ValueError if the transition is illegal.
        Per Section 06.3: no transition may bypass authorization,
        compliance, or risk checks.
        """
        if not self._can_transition(target):
            raise ValueError(f"Illegal session transition: {self.state.value} -> {target.value}")
        started_at = self.started_at
        stopped_at = self.stopped_at
        if target is SessionState.RUNNING and started_at is None:
            started_at = datetime.now(UTC)
        if (
            target in (SessionState.COMPLETED, SessionState.CANCELLED, SessionState.SAFE_HALT)
            and stopped_at is None
        ):
            stopped_at = datetime.now(UTC)
        return TradingSession(
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            profile_id=self.profile_id,
            strategy_version=self.strategy_version,
            exchange=self.exchange,
            instruments=self.instruments,
            capital_allocation=self.capital_allocation,
            risk_policy_id=self.risk_policy_id,
            state=target,
            created_at=self.created_at,
            started_at=started_at,
            stopped_at=stopped_at,
            error_detail=self.error_detail,
        )

    def with_error(self, detail: str) -> TradingSession:
        """Return a copy with an error detail set (for DEGRADED/SAFE_HALT)."""
        return TradingSession(
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            profile_id=self.profile_id,
            strategy_version=self.strategy_version,
            exchange=self.exchange,
            instruments=self.instruments,
            capital_allocation=self.capital_allocation,
            risk_policy_id=self.risk_policy_id,
            state=self.state,
            created_at=self.created_at,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            error_detail=detail,
        )

    @property
    def is_terminal(self) -> bool:
        """True if the session is in a terminal state."""
        return self.state in (SessionState.COMPLETED, SessionState.CANCELLED)

    @property
    def is_halted(self) -> bool:
        """True if the session is in SAFE_HALT."""
        return self.state is SessionState.SAFE_HALT
