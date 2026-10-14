"""Central policy engine with deny-by-default semantics.

Architecture Decisions: AD-010 (Zero-Trust), deny-by-default.

The policy engine evaluates authorization requests against a set of
rules. If no rule matches (or all matching rules are DENY), the
request is denied. Rules are evaluated in order of insertion; the
first matching ALLOW rule wins.

Pre-configured default rules for the identity domain:
- tenant-access: ALLOW when subject's tenant matches resource's tenant
- admin-privilege: ALLOW when subject role is admin or owner
- trader-execute: ALLOW when subject role is trader+ and action is execute_order
- viewer-read: ALLOW when action is read (any role)
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from contracts.identity import UserRole
from contracts.policy import PolicyEffect, PolicyRule

# Type alias for the condition callable.
Condition = Callable[[dict[str, Any]], bool]


@dataclass
class EngineRule:
    """Internal rule representation with optional condition."""

    name: str
    effect: PolicyEffect
    resource_pattern: str
    action: str
    condition: Condition | None = None
    description: str = ""


@dataclass(frozen=True)
class PolicyDecision:
    """Result of evaluating a policy request."""

    effect: PolicyEffect
    rule_name: str
    reason: str


class PolicyEngine:
    """Central authorization policy engine (deny-by-default).

    The engine starts with NO rules. If no matching ALLOW rule is
    found, the request is DENIED.
    """

    def __init__(self) -> None:
        self._rules: list[EngineRule] = []

    def add_rule(
        self,
        rule: PolicyRule,
        condition: Condition | None = None,
    ) -> None:
        """Add a rule to the engine.

        If a rule with the same name already exists, it is replaced.
        """
        self.remove_rule(rule.name)
        self._rules.append(
            EngineRule(
                name=rule.name,
                effect=rule.effect,
                resource_pattern=rule.resource_pattern,
                action=rule.action,
                condition=condition,
                description=rule.description,
            )
        )

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name. Returns True if a rule was removed."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def list_rules(self) -> list[EngineRule]:
        """Return all rules currently in the engine."""
        return list(self._rules)

    def reset(self) -> None:
        """Clear all rules."""
        self._rules.clear()

    def evaluate(
        self,
        subject: dict[str, Any],
        action: str,
        resource: str,
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Evaluate a policy request.

        Returns a :class:`PolicyDecision` with the effect and the
        matching rule name (or 'deny-default' if no rule matched).
        """
        ctx = context or {}
        for rule in self._rules:
            if not self._matches(rule, subject, action, resource, ctx):
                continue
            if rule.effect == PolicyEffect.ALLOW:
                return PolicyDecision(
                    effect=PolicyEffect.ALLOW,
                    rule_name=rule.name,
                    reason=f"Allowed by rule: {rule.name}",
                )
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                rule_name=rule.name,
                reason=f"Denied by rule: {rule.name}",
            )
        return PolicyDecision(
            effect=PolicyEffect.DENY,
            rule_name="deny-default",
            reason="No matching allow rule (deny-by-default)",
        )

    def _matches(
        self,
        rule: EngineRule,
        subject: dict[str, Any],
        action: str,
        resource: str,
        context: dict[str, Any],
    ) -> bool:
        """Check if a rule matches the request."""
        if not fnmatch.fnmatch(action, rule.action):
            return False
        if not fnmatch.fnmatch(resource, rule.resource_pattern):
            return False
        if rule.condition is not None:
            try:
                if not rule.condition(
                    {**subject, **context, "action": action, "resource": resource}
                ):
                    return False
            except Exception:
                return False
        return True


# ── Default identity-domain rules ──


def _tenant_access_condition(params: dict[str, Any]) -> bool:
    """ALLOW when subject's tenant matches resource's tenant."""
    subject_tenant = params.get("tenant_id")
    resource_tenant = params.get("resource_tenant_id")
    return subject_tenant is not None and subject_tenant == resource_tenant


def _admin_privilege_condition(params: dict[str, Any]) -> bool:
    """ALLOW when subject role is admin or owner."""
    role = params.get("role")
    if role is None:
        return False
    if isinstance(role, UserRole):
        return role in (UserRole.ADMIN, UserRole.OWNER)
    return role in ("admin", "owner")


def _trader_execute_condition(params: dict[str, Any]) -> bool:
    """ALLOW when subject role is trader+ and action is execute_order."""
    role = params.get("role")
    if role is None:
        return False
    if isinstance(role, UserRole):
        role_val = role
    else:
        try:
            role_val = UserRole(role)
        except ValueError:
            return False
    from contracts.identity import ROLE_PRIVILEGE_LEVEL  # noqa: PLC0415

    return (
        ROLE_PRIVILEGE_LEVEL.get(role_val, 0) >= ROLE_PRIVILEGE_LEVEL[UserRole.TRADER]
        and params.get("action") == "execute_order"
    )


def _viewer_read_condition(params: dict[str, Any]) -> bool:
    """ALLOW when action is 'read' (any role)."""
    return params.get("action") == "read"


def _get_default_rules() -> list[tuple[PolicyRule, Condition | None]]:
    """Return the default identity-domain rules with conditions."""
    return [
        (
            PolicyRule(
                name="tenant-access",
                effect=PolicyEffect.ALLOW,
                resource_pattern="*",
                action="*",
                description="ALLOW when subject's tenant matches resource's tenant",
            ),
            _tenant_access_condition,
        ),
        (
            PolicyRule(
                name="admin-privilege",
                effect=PolicyEffect.ALLOW,
                resource_pattern="*",
                action="*",
                description="ALLOW when subject role is admin or owner",
            ),
            _admin_privilege_condition,
        ),
        (
            PolicyRule(
                name="trader-execute",
                effect=PolicyEffect.ALLOW,
                resource_pattern="*",
                action="execute_order",
                description="ALLOW when subject role is trader+ and action is execute_order",
            ),
            _trader_execute_condition,
        ),
        (
            PolicyRule(
                name="viewer-read",
                effect=PolicyEffect.ALLOW,
                resource_pattern="*",
                action="read",
                description="ALLOW when action is read (any role)",
            ),
            _viewer_read_condition,
        ),
    ]


# ── Module-level singleton ──

_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    """Return the singleton policy engine with default rules loaded."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = PolicyEngine()
        for rule, cond in _get_default_rules():
            _engine.add_rule(rule, condition=cond)
    return _engine


def reset_policy_engine() -> None:
    """Reset the singleton policy engine (for testing)."""
    global _engine  # noqa: PLW0603
    _engine = None
