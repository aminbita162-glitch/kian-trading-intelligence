"""E4 — Policy-as-code tests.

Per E4 (Safety Plane Hardening): risk policies must be declarative
(policy-as-code) rather than hard-coded in the kernel's check methods.

Tests:
- Standard policy with all-passing context approves
- Individual rule denial blocks the order
- Disabled rules are skipped
- Empty policy with deny_if_empty=True denies (fail-closed)
- Empty policy with deny_if_empty=False approves (permissive)
- Custom rules can be added
- Rule order matters (first denial wins)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from contracts.policy_as_code import (
    PolicyAsCodeContext,
    PolicyAsCodeEffect,
    PolicyAsCodePolicy,
    PolicyAsCodeResult,
    PolicyAsCodeRule,
    check_concentration_limit,
    check_emergency_stop,
    check_exposure_limit,
    create_standard_risk_policy,
)


def _make_ctx(  # noqa: PLR0913
    *,
    side: str = "buy",
    order_value: str = "1000",
    current_exposure: str = "0",
    daily_loss: str = "0",
    max_exposure: str = "100000",
    max_daily_loss: str = "5000",
    max_drawdown: str = "10000",
    max_concentration_pct: str = "25.0",
    max_position_per_symbol: int = 10,
    min_liquidity_usd: str = "10000",
    max_volatility: str = "0.05",
    emergency_stop_active: bool = False,
    session_is_terminal: bool = False,
    session_is_halted: bool = False,
) -> PolicyAsCodeContext:
    """Create a policy-as-code context for testing."""
    return PolicyAsCodeContext(
        tenant_id="tenant-001",
        symbol="BTC/USDT",
        side=side,
        quantity="1.0",
        current_price="50000",
        order_value=Decimal(order_value),
        current_exposure=Decimal(current_exposure),
        daily_loss=Decimal(daily_loss),
        max_exposure=Decimal(max_exposure),
        max_daily_loss=Decimal(max_daily_loss),
        max_drawdown=Decimal(max_drawdown),
        max_concentration_pct=Decimal(max_concentration_pct),
        max_position_per_symbol=max_position_per_symbol,
        min_liquidity_usd=Decimal(min_liquidity_usd),
        max_volatility=Decimal(max_volatility),
        emergency_stop_active=emergency_stop_active,
        session_is_terminal=session_is_terminal,
        session_is_halted=session_is_halted,
    )


class TestStandardPolicy:
    """Test the standard risk policy with all default rules."""

    def test_all_passing_approves(self) -> None:
        """A context where all checks pass must be approved."""
        policy = create_standard_risk_policy()
        ctx = _make_ctx()
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.APPROVE
        assert "all-rules-passed" in result.rule_name

    def test_emergency_stop_denies_buy(self) -> None:
        """Emergency stop active + buy order must be denied."""
        policy = create_standard_risk_policy()
        ctx = _make_ctx(emergency_stop_active=True, side="buy")
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "emergency_stop"

    def test_emergency_stop_allows_sell(self) -> None:
        """Emergency stop active + sell order must be allowed (not exposure-increasing)."""
        policy = create_standard_risk_policy()
        ctx = _make_ctx(emergency_stop_active=True, side="sell")
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.APPROVE

    def test_session_terminal_denies(self) -> None:
        """Terminal session must be denied."""
        policy = create_standard_risk_policy()
        ctx = _make_ctx(session_is_terminal=True)
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "session_state"

    def test_session_halted_denies(self) -> None:
        """Halted session must be denied."""
        policy = create_standard_risk_policy()
        ctx = _make_ctx(session_is_halted=True)
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "session_state"

    def test_exposure_limit_denies(self) -> None:
        """Exceeding exposure limit must be denied."""
        policy = create_standard_risk_policy()
        ctx = _make_ctx(current_exposure="99000", order_value="2000", max_exposure="100000")
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "exposure_limit"

    def test_daily_loss_limit_denies(self) -> None:
        """Exceeding daily loss limit must be denied."""
        policy = create_standard_risk_policy()
        ctx = _make_ctx(daily_loss="5000", max_daily_loss="5000")
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "daily_loss_limit"

    def test_drawdown_limit_denies(self) -> None:
        """Exceeding drawdown limit must be denied."""
        policy = create_standard_risk_policy()
        # daily_loss=9000 < max_daily_loss=10000 but > max_drawdown=5000
        ctx = _make_ctx(daily_loss="9000", max_daily_loss="10000", max_drawdown="5000")
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "drawdown_limit"

    def test_concentration_limit_denies(self) -> None:
        """Exceeding concentration percentage must be denied."""
        policy = create_standard_risk_policy()
        # order_value=30000, max_exposure=100000 → 30% > 25%
        ctx = _make_ctx(order_value="30000", max_exposure="100000", max_concentration_pct="25.0")
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "concentration_limit"


class TestPolicyConfiguration:
    """Test policy configuration and rule management."""

    def test_disabled_rule_skipped(self) -> None:
        """A disabled rule must be skipped during evaluation."""
        policy = create_standard_risk_policy()
        # Disable the emergency_stop rule
        for rule in policy.rules:
            if rule.name == "emergency_stop":
                rule.enabled = False
        ctx = _make_ctx(emergency_stop_active=True, side="buy")
        result = policy.evaluate(ctx)
        # Since emergency_stop is disabled, it should pass (no other rule blocks it)
        assert result.effect is PolicyAsCodeEffect.APPROVE

    def test_empty_policy_deny_by_default(self) -> None:
        """Empty policy with deny_if_empty=True must deny (fail-closed)."""
        policy = PolicyAsCodePolicy(name="empty", version=1, rules=[], deny_if_empty=True)
        ctx = _make_ctx()
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "deny-empty-policy"

    def test_empty_policy_permissive(self) -> None:
        """Empty policy with deny_if_empty=False must approve."""
        policy = PolicyAsCodePolicy(name="empty", version=1, rules=[], deny_if_empty=False)
        ctx = _make_ctx()
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.APPROVE

    def test_custom_rule_added(self) -> None:
        """A custom rule can be added to a policy."""
        custom_rule = PolicyAsCodeRule(
            name="custom_check",
            check=lambda ctx: PolicyAsCodeResult(
                effect=PolicyAsCodeEffect.DENY,
                rule_name="custom_check",
                reason="Custom check failed.",
            ),
            description="A custom denial rule.",
        )
        policy = PolicyAsCodePolicy(name="custom", version=1, rules=[custom_rule])
        ctx = _make_ctx()
        result = policy.evaluate(ctx)
        assert result.effect is PolicyAsCodeEffect.DENY
        assert result.rule_name == "custom_check"

    def test_rule_order_matters(self) -> None:
        """The first denial in order stops evaluation."""
        deny1 = PolicyAsCodeRule(
            name="deny1",
            check=lambda ctx: PolicyAsCodeResult(
                effect=PolicyAsCodeEffect.DENY,
                rule_name="deny1",
                reason="First denial.",
            ),
        )
        deny2 = PolicyAsCodeRule(
            name="deny2",
            check=lambda ctx: PolicyAsCodeResult(
                effect=PolicyAsCodeEffect.DENY,
                rule_name="deny2",
                reason="Second denial.",
            ),
        )
        policy = PolicyAsCodePolicy(name="ordered", version=1, rules=[deny1, deny2])
        ctx = _make_ctx()
        result = policy.evaluate(ctx)
        assert result.rule_name == "deny1"

    def test_duplicate_rule_names_rejected(self) -> None:
        """Duplicate rule names in a policy must be rejected."""
        rule1 = PolicyAsCodeRule(
            name="dup",
            check=lambda ctx: PolicyAsCodeResult(
                effect=PolicyAsCodeEffect.APPROVE,
                rule_name="dup",
                reason="ok",
            ),
        )
        rule2 = PolicyAsCodeRule(
            name="dup",
            check=lambda ctx: PolicyAsCodeResult(
                effect=PolicyAsCodeEffect.APPROVE,
                rule_name="dup",
                reason="ok",
            ),
        )
        with pytest.raises(ValueError, match="Duplicate rule names"):
            PolicyAsCodePolicy(name="dup-policy", version=1, rules=[rule1, rule2])

    def test_policy_version_must_be_positive(self) -> None:
        """Policy version must be >= 1."""
        with pytest.raises(ValueError, match="version must be >= 1"):
            PolicyAsCodePolicy(name="zero", version=0)


class TestIndividualRules:
    """Test individual rule functions in isolation."""

    def test_emergency_stop_sell_ok(self) -> None:
        """Emergency stop allows sell orders (not exposure-increasing)."""
        ctx = _make_ctx(emergency_stop_active=True, side="sell")
        result = check_emergency_stop(ctx)
        assert result.effect is PolicyAsCodeEffect.APPROVE

    def test_exposure_limit_sell_ok(self) -> None:
        """Exposure limit does not apply to sell orders."""
        ctx = _make_ctx(side="sell", current_exposure="999999", order_value="999999")
        result = check_exposure_limit(ctx)
        assert result.effect is PolicyAsCodeEffect.APPROVE

    def test_concentration_sell_ok(self) -> None:
        """Concentration limit does not apply to sell orders."""
        ctx = _make_ctx(side="sell", order_value="999999", max_exposure="100")
        result = check_concentration_limit(ctx)
        assert result.effect is PolicyAsCodeEffect.APPROVE
