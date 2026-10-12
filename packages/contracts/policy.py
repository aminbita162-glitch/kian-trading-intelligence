"""Policy contracts for Kian Trading Intelligence.

Defines the core policy engine types: PolicyEffect, PolicyRule, and
PolicyDecision. These are shared between the policy engine and its
consumers.

Architecture Decisions: AD-010 (Zero-Trust), deny-by-default.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PolicyEffect(StrEnum):
    """Effect of a policy rule evaluation."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyRule:
    """A single policy rule.

    Attributes:
        name: Human-readable rule name.
        effect: ALLOW or DENY.
        resource_pattern: Glob-style pattern for matching resources.
        action: The action this rule applies to (e.g. 'read', 'execute_order').
        description: Optional human-readable description.
    """

    name: str
    effect: PolicyEffect
    resource_pattern: str
    action: str
    description: str = ""


@dataclass(frozen=True)
class PolicyDecision:
    """Result of evaluating a policy request.

    Attributes:
        effect: ALLOW or DENY.
        rule_name: The name of the matching rule, or 'deny-default'.
        reason: Human-readable explanation of the decision.
    """

    effect: PolicyEffect
    rule_name: str
    reason: str
