"""Enumerations for Kian Trading Intelligence contracts.

Architecture Decisions: AD-003, AD-004, AD-014, AD-017, AD-021.
"""

from __future__ import annotations

from enum import StrEnum


class OperatingMode(StrEnum):
    """Platform operating mode per Section 01.3.

    A mode change must never silently enable real-money trading.
    """

    SIMULATION = "simulation"
    PAPER = "paper"
    LIVE = "live"


class OrderState(StrEnum):
    """Order lifecycle states per Section 05.2.

    All legal transitions must be defined and tested.
    """

    CREATED = "created"
    VALIDATED = "validated"
    RISK_APPROVED = "risk_approved"
    SUBMISSION_PENDING = "submission_pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN_OUTCOME = "unknown_outcome"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    SAFE_HALT = "safe_halt"


class SessionState(StrEnum):
    """Trading session states per Section 06.2.

    Sessions require authorization and preflight checks.
    """

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PREFLIGHT = "preflight"
    AWAITING_USER_APPROVAL = "awaiting_user_approval"
    RUNNING = "running"
    DEGRADED = "degraded"
    SAFE_HALT = "safe_halt"
    RECONCILING = "reconciling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ── Legal Order State Transitions ──
# Maps each state to the set of states it may legally transition to.
LEGAL_ORDER_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.CREATED: {
        OrderState.VALIDATED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
    },
    OrderState.VALIDATED: {
        OrderState.RISK_APPROVED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
    },
    OrderState.RISK_APPROVED: {
        OrderState.SUBMISSION_PENDING,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    },
    OrderState.SUBMISSION_PENDING: {
        OrderState.SUBMITTED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
        OrderState.SAFE_HALT,
    },
    OrderState.SUBMITTED: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
        OrderState.UNKNOWN_OUTCOME,
        OrderState.SAFE_HALT,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.UNKNOWN_OUTCOME,
        OrderState.RECONCILIATION_REQUIRED,
        OrderState.SAFE_HALT,
    },
    OrderState.FILLED: set(),  # terminal
    OrderState.CANCELLED: set(),  # terminal
    OrderState.REJECTED: set(),  # terminal
    OrderState.EXPIRED: set(),  # terminal
    OrderState.UNKNOWN_OUTCOME: {
        OrderState.RECONCILIATION_REQUIRED,
        OrderState.SAFE_HALT,
    },
    OrderState.RECONCILIATION_REQUIRED: {
        OrderState.FILLED,
        OrderState.PARTIALLY_FILLED,
        OrderState.CANCELLED,
        OrderState.SAFE_HALT,
    },
    OrderState.SAFE_HALT: {
        OrderState.RECONCILIATION_REQUIRED,
    },
}
