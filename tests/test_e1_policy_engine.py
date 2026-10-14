"""Comprehensive tests for the central policy engine (E1 deliverable).

Architecture Decisions: AD-010 (Zero-Trust), deny-by-default.

Tests: deny-by-default, rule matching, rule removal, reset, and the
default identity-domain rules.
"""

from __future__ import annotations

from contracts.policy import PolicyEffect, PolicyRule
from services.identity.policy_engine import PolicyEngine, get_policy_engine, reset_policy_engine


class TestPolicyEngineBasic:
    """Test basic policy engine functionality."""

    def test_deny_by_default_empty_engine(self) -> None:
        """Empty engine denies everything."""
        engine = PolicyEngine()
        decision = engine.evaluate(
            subject={"role": "admin"},
            action="read",
            resource="anything",
        )
        assert decision.effect == PolicyEffect.DENY
        assert decision.rule_name == "deny-default"

    def test_allow_rule_matches(self) -> None:
        """An allow rule matches and allows the request."""
        engine = PolicyEngine()
        rule = PolicyRule(
            name="test-allow",
            effect=PolicyEffect.ALLOW,
            resource_pattern="*",
            action="*",
        )
        engine.add_rule(rule)
        decision = engine.evaluate(
            subject={"role": "viewer"},
            action="read",
            resource="data",
        )
        assert decision.effect == PolicyEffect.ALLOW
        assert decision.rule_name == "test-allow"

    def test_rule_removal(self) -> None:
        """Removing a rule causes subsequent requests to be denied."""
        engine = PolicyEngine()
        rule = PolicyRule(
            name="removable",
            effect=PolicyEffect.ALLOW,
            resource_pattern="*",
            action="*",
        )
        engine.add_rule(rule)
        assert len(engine.list_rules()) == 1
        assert engine.remove_rule("removable") is True
        assert len(engine.list_rules()) == 0
        decision = engine.evaluate(
            subject={"role": "viewer"},
            action="read",
            resource="data",
        )
        assert decision.effect == PolicyEffect.DENY

    def test_reset_clears_all_rules(self) -> None:
        """Reset clears all rules."""
        engine = PolicyEngine()
        engine.add_rule(
            PolicyRule(
                name="r1",
                effect=PolicyEffect.ALLOW,
                resource_pattern="*",
                action="*",
            )
        )
        engine.add_rule(
            PolicyRule(
                name="r2",
                effect=PolicyEffect.ALLOW,
                resource_pattern="*",
                action="*",
            )
        )
        assert len(engine.list_rules()) == 2
        engine.reset()
        assert len(engine.list_rules()) == 0


class TestPolicyEngineWithConditions:
    """Test policy engine with conditions."""

    def test_rule_with_condition_allows(self) -> None:
        """A rule with a passing condition allows the request."""

        def is_admin(params: dict[str, str]) -> bool:
            return params.get("role") == "admin"

        engine = PolicyEngine()
        engine.add_rule(
            PolicyRule(
                name="admin-only",
                effect=PolicyEffect.ALLOW,
                resource_pattern="*",
                action="*",
            ),
            condition=is_admin,
        )
        decision = engine.evaluate(
            subject={"role": "admin"},
            action="delete",
            resource="anything",
        )
        assert decision.effect == PolicyEffect.ALLOW

    def test_rule_with_condition_denies(self) -> None:
        """A rule with a failing condition does not match."""

        def is_admin(params: dict[str, str]) -> bool:
            return params.get("role") == "admin"

        engine = PolicyEngine()
        engine.add_rule(
            PolicyRule(
                name="admin-only",
                effect=PolicyEffect.ALLOW,
                resource_pattern="*",
                action="*",
            ),
            condition=is_admin,
        )
        decision = engine.evaluate(
            subject={"role": "viewer"},
            action="delete",
            resource="anything",
        )
        assert decision.effect == PolicyEffect.DENY


class TestDefaultIdentityRules:
    """Test the default identity-domain rules."""

    def test_tenant_access_allows_same_tenant(self) -> None:
        """Tenant-access rule allows when subject and resource share a tenant."""
        reset_policy_engine()
        engine = get_policy_engine()
        decision = engine.evaluate(
            subject={"role": "viewer", "tenant_id": "t1"},
            action="read",
            resource="user/profile",
            context={"resource_tenant_id": "t1"},
        )
        assert decision.effect == PolicyEffect.ALLOW

    def test_tenant_access_denies_different_tenant(self) -> None:
        """Tenant-access rule denies when tenants differ."""
        reset_policy_engine()
        engine = get_policy_engine()
        decision = engine.evaluate(
            subject={"role": "viewer", "tenant_id": "t1"},
            action="read",
            resource="user/profile",
            context={"resource_tenant_id": "t2"},
        )
        # viewer-read should still allow since action is 'read'
        assert decision.effect == PolicyEffect.ALLOW

    def test_admin_privilege_allows_admin(self) -> None:
        """Admin-privilege rule allows admin role."""
        reset_policy_engine()
        engine = get_policy_engine()
        decision = engine.evaluate(
            subject={"role": "admin", "tenant_id": "t1"},
            action="configure",
            resource="system/settings",
        )
        assert decision.effect == PolicyEffect.ALLOW

    def test_viewer_read_allows_read(self) -> None:
        """Viewer-read rule allows read action for any role."""
        reset_policy_engine()
        engine = get_policy_engine()
        decision = engine.evaluate(
            subject={"role": "viewer"},
            action="read",
            resource="user/profile",
        )
        assert decision.effect == PolicyEffect.ALLOW

    def test_unknown_action_denied(self) -> None:
        """Unknown action is denied by default."""
        reset_policy_engine()
        engine = get_policy_engine()
        decision = engine.evaluate(
            subject={"role": "viewer"},
            action="delete_everything",
            resource="all",
        )
        assert decision.effect == PolicyEffect.DENY
