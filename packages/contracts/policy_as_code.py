"""Policy-as-code contracts for the Risk Kernel.

Per E4 (Safety Plane Hardening): risk policies must be expressible as
declarative code (policy-as-code) rather than hard-coded in the kernel's
check methods.  This module defines the building blocks for declarative
risk policies that the kernel evaluates at assessment time.

Architecture Decisions: AD-004 (independent Risk Kernel), AD-013 (dynamic
risk management), AD-036 (signed risk tokens + policy-as-code).

A policy-as-code rule is a :class:`PolicyAsCodeRule` that pairs a
human-readable name with a :class:`RiskCheckFn` — a pure function that
receives the order context and returns a :class:`PolicyAsCodeResult`
(approve or deny with a reason).  The kernel evaluates rules in order
and returns on the first denial.  If no rule denies, the assessment is
approved.

This is distinct from the identity-domain :class:`~contracts.policy.PolicyRule`
/ :class:`~services.identity.policy_engine.PolicyEngine` (deny-by-default
RBAC).  The risk policy-as-code layer is about financial safety limits,
not access control.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class PolicyAsCodeEffect(StrEnum):
    """Effect of a policy-as-code rule evaluation."""

    APPROVE = "approve"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyAsCodeContext:
    """Context passed to each policy-as-code rule.

    Attributes:
        tenant_id: Tenant scope.
        symbol: Trading symbol.
        side: Order side ("buy" or "sell").
        quantity: Order quantity (string for exact decimal).
        current_price: Current market price (string).
        order_value: Computed order value (quantity * current_price).
        current_exposure: Current total exposure for the tenant.
        daily_loss: Current daily realized loss for the tenant.
        max_exposure: Policy max_position_value.
        max_daily_loss: Policy max_daily_loss.
        max_drawdown: Policy max_drawdown.
        max_concentration_pct: Policy max_concentration_pct.
        max_position_per_symbol: Policy max_position_per_symbol.
        min_liquidity_usd: Policy min_liquidity_usd.
        max_volatility: Policy max_volatility.
        emergency_stop_active: Whether emergency stop is active.
        session_is_terminal: Whether the session is in a terminal state.
        session_is_halted: Whether the session is in SAFE_HALT.
    """

    tenant_id: str
    symbol: str
    side: str
    quantity: str
    current_price: str
    order_value: Decimal
    current_exposure: Decimal
    daily_loss: Decimal
    max_exposure: Decimal
    max_daily_loss: Decimal
    max_drawdown: Decimal
    max_concentration_pct: Decimal
    max_position_per_symbol: int
    min_liquidity_usd: Decimal
    max_volatility: Decimal
    emergency_stop_active: bool
    session_is_terminal: bool
    session_is_halted: bool


@dataclass(frozen=True)
class PolicyAsCodeResult:
    """Result of evaluating a single policy-as-code rule.

    Attributes:
        effect: APPROVE or DENY.
        rule_name: Name of the rule that produced this result.
        reason: Human-readable explanation.
    """

    effect: PolicyAsCodeEffect
    rule_name: str
    reason: str

    @property
    def is_denied(self) -> bool:
        """True if this result denies the order."""
        return self.effect is PolicyAsCodeEffect.DENY


# Type alias for a risk check function.
RiskCheckFn = Callable[[PolicyAsCodeContext], PolicyAsCodeResult]


@dataclass
class PolicyAsCodeRule:
    """A single declarative risk policy rule.

    Attributes:
        name: Human-readable rule name (must be unique within a policy).
        check: The function that evaluates the rule.
        description: Optional human-readable description.
        enabled: If False, the rule is skipped during evaluation.
    """

    name: str
    check: RiskCheckFn
    description: str = ""
    enabled: bool = True


@dataclass
class PolicyAsCodePolicy:
    """A collection of policy-as-code rules forming a complete risk policy.

    Rules are evaluated in order. The first DENY result stops evaluation
    and the assessment is denied. If all enabled rules APPROVE (or there
    are no rules), the assessment is approved.

    Attributes:
        name: Policy name.
        version: Policy version (monotonically increasing).
        rules: Ordered list of rules.
        deny_if_empty: If True and no rules are enabled, deny (fail-closed).
            If False, approve when no rules are enabled (permissive).
            Default: True (fail-closed for safety).
    """

    name: str
    version: int
    rules: list[PolicyAsCodeRule] = field(default_factory=list)
    deny_if_empty: bool = True

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("Policy version must be >= 1.")
        names = [r.name for r in self.rules]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate rule names in policy.")

    def evaluate(self, ctx: PolicyAsCodeContext) -> PolicyAsCodeResult:
        """Evaluate all enabled rules in order.

        Returns the first DENY result, or an APPROVE if all pass.
        """
        active_rules = [r for r in self.rules if r.enabled]
        if not active_rules:
            if self.deny_if_empty:
                return PolicyAsCodeResult(
                    effect=PolicyAsCodeEffect.DENY,
                    rule_name="deny-empty-policy",
                    reason="No active rules — fail-closed by default.",
                )
            return PolicyAsCodeResult(
                effect=PolicyAsCodeEffect.APPROVE,
                rule_name="empty-policy-approve",
                reason="No active rules — permissive.",
            )

        for rule in active_rules:
            result = rule.check(ctx)
            if result.is_denied:
                return result

        return PolicyAsCodeResult(
            effect=PolicyAsCodeEffect.APPROVE,
            rule_name="all-rules-passed",
            reason="All policy-as-code rules approved.",
        )


# ── Standard policy-as-code rules ──


def check_emergency_stop(ctx: PolicyAsCodeContext) -> PolicyAsCodeResult:
    """Rule: emergency stop blocks new exposure-increasing orders."""
    if ctx.emergency_stop_active and ctx.side == "buy":
        return PolicyAsCodeResult(
            effect=PolicyAsCodeEffect.DENY,
            rule_name="emergency_stop",
            reason="Emergency stop is active — new exposure-increasing orders blocked.",
        )
    return PolicyAsCodeResult(
        effect=PolicyAsCodeEffect.APPROVE,
        rule_name="emergency_stop",
        reason="Emergency stop not active or order is not exposure-increasing.",
    )


def check_session_state(ctx: PolicyAsCodeContext) -> PolicyAsCodeResult:
    """Rule: session must not be terminal or halted."""
    if ctx.session_is_terminal:
        return PolicyAsCodeResult(
            effect=PolicyAsCodeEffect.DENY,
            rule_name="session_state",
            reason="Session is terminal — new orders blocked.",
        )
    if ctx.session_is_halted:
        return PolicyAsCodeResult(
            effect=PolicyAsCodeEffect.DENY,
            rule_name="session_state",
            reason="Session is in SAFE_HALT — new orders blocked.",
        )
    return PolicyAsCodeResult(
        effect=PolicyAsCodeEffect.APPROVE,
        rule_name="session_state",
        reason="Session state allows new orders.",
    )


def check_exposure_limit(ctx: PolicyAsCodeContext) -> PolicyAsCodeResult:
    """Rule: exposure must not exceed the policy limit."""
    if ctx.side == "buy":
        new_exposure = ctx.current_exposure + ctx.order_value
        if new_exposure > ctx.max_exposure:
            return PolicyAsCodeResult(
                effect=PolicyAsCodeEffect.DENY,
                rule_name="exposure_limit",
                reason=(
                    f"Exposure {new_exposure} exceeds limit {ctx.max_exposure} "
                    f"(current: {ctx.current_exposure}, order: {ctx.order_value})."
                ),
            )
    return PolicyAsCodeResult(
        effect=PolicyAsCodeEffect.APPROVE,
        rule_name="exposure_limit",
        reason="Exposure within limits.",
    )


def check_daily_loss_limit(ctx: PolicyAsCodeContext) -> PolicyAsCodeResult:
    """Rule: daily loss must not exceed the policy limit."""
    if ctx.daily_loss >= ctx.max_daily_loss:
        return PolicyAsCodeResult(
            effect=PolicyAsCodeEffect.DENY,
            rule_name="daily_loss_limit",
            reason=(
                f"Daily loss {ctx.daily_loss} exceeds limit {ctx.max_daily_loss}. "
                "Trading stopped for the day."
            ),
        )
    return PolicyAsCodeResult(
        effect=PolicyAsCodeEffect.APPROVE,
        rule_name="daily_loss_limit",
        reason="Daily loss within limits.",
    )


def check_drawdown_limit(ctx: PolicyAsCodeContext) -> PolicyAsCodeResult:
    """Rule: drawdown must not exceed the policy limit."""
    if ctx.daily_loss >= ctx.max_drawdown:
        return PolicyAsCodeResult(
            effect=PolicyAsCodeEffect.DENY,
            rule_name="drawdown_limit",
            reason=f"Drawdown {ctx.daily_loss} exceeds limit {ctx.max_drawdown}.",
        )
    return PolicyAsCodeResult(
        effect=PolicyAsCodeEffect.APPROVE,
        rule_name="drawdown_limit",
        reason="Drawdown within limits.",
    )


def check_concentration_limit(ctx: PolicyAsCodeContext) -> PolicyAsCodeResult:
    """Rule: concentration must not exceed the policy percentage."""
    if ctx.side == "buy" and ctx.max_exposure > 0:
        conc_pct = (ctx.order_value / ctx.max_exposure) * Decimal(100)
        if conc_pct > ctx.max_concentration_pct:
            return PolicyAsCodeResult(
                effect=PolicyAsCodeEffect.DENY,
                rule_name="concentration_limit",
                reason=f"Concentration {conc_pct}% exceeds limit {ctx.max_concentration_pct}%.",
            )
    return PolicyAsCodeResult(
        effect=PolicyAsCodeEffect.APPROVE,
        rule_name="concentration_limit",
        reason="Concentration within limits.",
    )


# ── Standard policy factory ──


def create_standard_risk_policy(
    *,
    name: str = "standard-risk-policy",
    version: int = 1,
) -> PolicyAsCodePolicy:
    """Create the standard risk policy with all default rules.

    The standard policy includes:
    1. emergency_stop — blocks exposure-increasing orders when e-stop active
    2. session_state — blocks orders when session is terminal/halted
    3. exposure_limit — blocks orders that exceed max exposure
    4. daily_loss_limit — blocks orders when daily loss exceeds limit
    5. drawdown_limit — blocks orders when drawdown exceeds limit
    6. concentration_limit — blocks orders that exceed concentration pct

    Returns a fail-closed policy (deny_if_empty=True).
    """
    return PolicyAsCodePolicy(
        name=name,
        version=version,
        rules=[
            PolicyAsCodeRule(
                name="emergency_stop",
                check=check_emergency_stop,
                description="Block exposure-increasing orders when emergency stop is active.",
            ),
            PolicyAsCodeRule(
                name="session_state",
                check=check_session_state,
                description="Block orders when session is terminal or in SAFE_HALT.",
            ),
            PolicyAsCodeRule(
                name="exposure_limit",
                check=check_exposure_limit,
                description="Block orders that exceed the maximum exposure limit.",
            ),
            PolicyAsCodeRule(
                name="daily_loss_limit",
                check=check_daily_loss_limit,
                description="Block orders when daily loss exceeds the limit.",
            ),
            PolicyAsCodeRule(
                name="drawdown_limit",
                check=check_drawdown_limit,
                description="Block orders when drawdown exceeds the limit.",
            ),
            PolicyAsCodeRule(
                name="concentration_limit",
                check=check_concentration_limit,
                description="Block orders that exceed the concentration percentage.",
            ),
        ],
        deny_if_empty=True,
    )
