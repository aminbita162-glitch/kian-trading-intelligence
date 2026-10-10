"""Agent contracts for Kian Trading Intelligence.

Per AD-004 (Four Agents + Independent Safety Kernel): implement exactly four
specialized agents plus a separate deterministic Risk & Safety Kernel. The
kernel is NOT an agent and is NOT a fifth agent.

Per AD-020 (Policy-Governed Agent Orchestration): use typed agent contracts,
explicit permissions, deterministic cross-verification, and independent risk
authorization. Agent failures must not expand privileges.

Per AD-022 (Observability, Audit): provide tamper-evident audit records and
decision traces for every agent action.

Per Section 04 — Four Specialized Agents:
1. Market Intelligence Agent — observations, features, bounded research.
   Prohibited: direct trade execution.
2. Strategy & Portfolio Agent — evaluation, portfolio, proposals.
   Prohibited: risk override or self-authorized execution.
3. Execution & Supervisor Agent — order lifecycle, adapter orchestration,
   reconciliation. Prohibited: bypassing risk authorization.
4. Mining Operations Agent — simulation, profitability, pool coordination.
   Prohibited: unrestricted trading-account access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class AgentType(StrEnum):
    """The four specialized agent types per AD-004."""

    MARKET_INTELLIGENCE = "market_intelligence"
    STRATEGY_PORTFOLIO = "strategy_portfolio"
    EXECUTION_SUPERVISOR = "execution_supervisor"
    MINING_OPERATIONS = "mining_operations"


class AgentPermission(StrEnum):
    """Permissions granted to agents per AD-020.

    An agent may only exercise permissions explicitly granted to its type.
    No agent may grant permissions to itself or to another agent.
    """

    # Market Intelligence Agent
    OBSERVE_MARKET = "observe_market"
    COMPUTE_FEATURES = "compute_features"
    RESEARCH_SUMMARY = "research_summary"

    # Strategy & Portfolio Agent
    EVALUATE_STRATEGY = "evaluate_strategy"
    PROPOSE_POSITION = "propose_position"
    VERSION_TRADE_INTENT = "version_trade_intent"

    # Execution & Supervisor Agent
    SUBMIT_ORDER = "submit_order"
    CANCEL_ORDER = "cancel_order"
    RECONCILE_ORDER = "reconcile_order"

    # Mining Operations Agent
    SIMULATE_MINING = "simulate_mining"
    ASSESS_PROFITABILITY = "assess_profitability"
    COORDINATE_POOL = "coordinate_pool"
    REPORT_SAFETY_TELEMETRY = "report_safety_telemetry"


class AgentProhibition(StrEnum):
    """Prohibited actions per agent type per Section 04.

    These are hard boundaries that no agent may cross regardless of
    configuration or runtime state.
    """

    DIRECT_TRADE_EXECUTION = "direct_trade_execution"
    RISK_OVERRIDE = "risk_override"
    SELF_AUTHORIZED_EXECUTION = "self_authorized_execution"
    BYPASS_RISK_AUTHORIZATION = "bypass_risk_authorization"
    UNRESTRICTED_TRADING_ACCOUNT_ACCESS = "unrestricted_trading_account_access"
    GRANT_PERMISSIONS = "grant_permissions"
    BYPASS_TOKEN_BUDGET = "bypass_token_budget"


# Per-agent permission sets — an agent may only exercise its granted permissions.
# Per AD-020: explicit permissions; agent failures must not expand privileges.
AGENT_PERMISSIONS: dict[AgentType, frozenset[AgentPermission]] = {
    AgentType.MARKET_INTELLIGENCE: frozenset(
        {
            AgentPermission.OBSERVE_MARKET,
            AgentPermission.COMPUTE_FEATURES,
            AgentPermission.RESEARCH_SUMMARY,
        }
    ),
    AgentType.STRATEGY_PORTFOLIO: frozenset(
        {
            AgentPermission.EVALUATE_STRATEGY,
            AgentPermission.PROPOSE_POSITION,
            AgentPermission.VERSION_TRADE_INTENT,
        }
    ),
    AgentType.EXECUTION_SUPERVISOR: frozenset(
        {
            AgentPermission.SUBMIT_ORDER,
            AgentPermission.CANCEL_ORDER,
            AgentPermission.RECONCILE_ORDER,
        }
    ),
    AgentType.MINING_OPERATIONS: frozenset(
        {
            AgentPermission.SIMULATE_MINING,
            AgentPermission.ASSESS_PROFITABILITY,
            AgentPermission.COORDINATE_POOL,
            AgentPermission.REPORT_SAFETY_TELEMETRY,
        }
    ),
}

# Per-agent prohibitions — these actions are explicitly forbidden per Section 04.
AGENT_PROHIBITIONS: dict[AgentType, frozenset[AgentProhibition]] = {
    AgentType.MARKET_INTELLIGENCE: frozenset(
        {
            AgentProhibition.DIRECT_TRADE_EXECUTION,
            AgentProhibition.GRANT_PERMISSIONS,
            AgentProhibition.BYPASS_TOKEN_BUDGET,
        }
    ),
    AgentType.STRATEGY_PORTFOLIO: frozenset(
        {
            AgentProhibition.RISK_OVERRIDE,
            AgentProhibition.SELF_AUTHORIZED_EXECUTION,
            AgentProhibition.GRANT_PERMISSIONS,
            AgentProhibition.BYPASS_TOKEN_BUDGET,
        }
    ),
    AgentType.EXECUTION_SUPERVISOR: frozenset(
        {
            AgentProhibition.BYPASS_RISK_AUTHORIZATION,
            AgentProhibition.GRANT_PERMISSIONS,
            AgentProhibition.BYPASS_TOKEN_BUDGET,
        }
    ),
    AgentType.MINING_OPERATIONS: frozenset(
        {
            AgentProhibition.UNRESTRICTED_TRADING_ACCOUNT_ACCESS,
            AgentProhibition.GRANT_PERMISSIONS,
            AgentProhibition.BYPASS_TOKEN_BUDGET,
        }
    ),
}


# Per-AD-004: the Risk Kernel is NOT an agent. This set defines exactly
# the four agent types; any code that checks "is this an agent?" must
# verify membership in this set and explicitly exclude the Risk Kernel.
ALL_AGENT_TYPES: frozenset[AgentType] = frozenset(AgentType)


@dataclass(frozen=True)
class AgentId:
    """Stable identity for an agent instance."""

    value: UUID

    @classmethod
    def generate(cls) -> AgentId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class DecisionTraceId:
    """Stable identity for a decision trace.

    Per deliverable 12: decision traceability — every agent decision
    must be auditable with a complete trace.
    """

    value: UUID

    @classmethod
    def generate(cls) -> DecisionTraceId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class DecisionTraceEntry:
    """A single entry in a decision trace.

    Per deliverable 12: decision traceability.
    Per AD-022: structured audit records.
    """

    step: str
    agent_type: AgentType
    permission: AgentPermission | None
    timestamp: datetime
    detail: str = ""
    data: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.step:
            raise ValueError("Trace entry step must not be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")


@dataclass
class DecisionTrace:
    """Complete trace of an agent decision pipeline.

    Per deliverable 12: decision traceability.
    Per AD-022: tamper-evident audit records. Entries are append-only;
    once recorded, entries cannot be modified or removed.
    """

    trace_id: DecisionTraceId
    tenant_id: str
    entries: list[DecisionTraceEntry] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    final_decision: str = ""
    final_authorized: bool = False
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    def add_entry(self, entry: DecisionTraceEntry) -> None:
        """Append a trace entry. Entries are append-only."""
        self.entries.append(entry)

    def complete(self, decision: str, authorized: bool) -> None:
        """Mark the trace as complete with the final decision."""
        self.final_decision = decision
        self.final_authorized = authorized
        self.completed_at = datetime.now(UTC)

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None


@dataclass
class AgentContext:
    """Context for an agent invocation.

    Per AD-020: typed agent contracts with explicit permissions.
    Per AD-002: tenant-scoped.
    Per AD-020: agent failures must not expand privileges.
    """

    agent_id: AgentId
    agent_type: AgentType
    tenant_id: str
    profile_id: str
    permissions: frozenset[AgentPermission] = field(default_factory=frozenset)
    session_id: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must not be empty.")
        if not self.profile_id:
            raise ValueError("profile_id must not be empty.")
        expected = AGENT_PERMISSIONS.get(self.agent_type, frozenset())
        if not self.permissions:
            object.__setattr__(self, "permissions", expected)
        extra = self.permissions - expected
        if extra:
            raise ValueError(
                f"Agent {self.agent_type.value} cannot have permissions: "
                f"{sorted(p.value for p in extra)}"
            )

    @property
    def prohibitions(self) -> frozenset[AgentProhibition]:
        return AGENT_PROHIBITIONS.get(self.agent_type, frozenset())

    def has_permission(self, permission: AgentPermission) -> bool:
        return permission in self.permissions

    def check_permission(self, permission: AgentPermission) -> None:
        """Raise PermissionError if the agent lacks the required permission."""
        if not self.has_permission(permission):
            raise PermissionError(
                f"Agent {self.agent_type.value} lacks permission {permission.value}."
            )

    def check_not_prohibited(self, action: AgentProhibition) -> None:
        """Raise PermissionError if the action is prohibited for this agent."""
        if action in self.prohibitions:
            raise PermissionError(
                f"Agent {self.agent_type.value} is prohibited from {action.value}."
            )

    def check_not_prohibited_direct_trade(self) -> None:
        """Convenience: check DIRECT_TRADE_EXECUTION prohibition."""
        self.check_not_prohibited(AgentProhibition.DIRECT_TRADE_EXECUTION)

    def check_not_prohibited_risk_override(self) -> None:
        """Convenience: check RISK_OVERRIDE prohibition."""
        self.check_not_prohibited(AgentProhibition.RISK_OVERRIDE)

    def check_not_prohibited_bypass_risk(self) -> None:
        """Convenience: check BYPASS_RISK_AUTHORIZATION prohibition."""
        self.check_not_prohibited(AgentProhibition.BYPASS_RISK_AUTHORIZATION)

    def check_not_prohibited_unrestricted_account(self) -> None:
        """Convenience: check UNRESTRICTED_TRADING_ACCOUNT_ACCESS prohibition."""
        self.check_not_prohibited(
            AgentProhibition.UNRESTRICTED_TRADING_ACCOUNT_ACCESS,
        )


@dataclass
class AgentResult:
    """Typed result from an agent operation.

    Per AD-020: agent failures must not expand privileges. A failed
    agent operation returns success=False; it does NOT grant additional
    permissions or bypass risk controls.
    """

    agent_type: AgentType
    success: bool
    data: dict[str, str] = field(default_factory=dict)
    error: str = ""
    trace_id: DecisionTraceId | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")

    @classmethod
    def failure(
        cls,
        agent_type: AgentType,
        error: str,
        trace_id: DecisionTraceId | None = None,
    ) -> AgentResult:
        return cls(
            agent_type=agent_type,
            success=False,
            error=error,
            trace_id=trace_id,
        )

    @classmethod
    def ok(
        cls,
        agent_type: AgentType,
        data: dict[str, str] | None = None,
        trace_id: DecisionTraceId | None = None,
    ) -> AgentResult:
        return cls(
            agent_type=agent_type,
            success=True,
            data=data or {},
            trace_id=trace_id,
        )
