"""Shared contracts for Kian Trading Intelligence.

This package contains Pydantic models and enumerations shared across
backend services, agents, and API boundaries.

Architecture Decisions: AD-003 (Hybrid Low-Token Intelligence),
AD-004 (Four Agents + Risk Kernel), AD-014 (Deterministic Execution),
AD-021 (Shared Market Data).
"""

from contracts.enums import OperatingMode, OrderState, SessionState
from contracts.identity import (
    ROLE_PRIVILEGE_LEVEL,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    AuthSession,
    CredentialType,
    Device,
    DeviceStatus,
    MFAMethod,
    SessionStatus,
    Tenant,
    TenantId,
    TradingProfile,
    User,
    UserId,
    UserRole,
    can_manage_role,
)
from contracts.mode import OperatingModeConfig
from contracts.order import OrderIntent, OrderIntentId

__all__ = [
    "OperatingMode",
    "OrderState",
    "SessionState",
    "OperatingModeConfig",
    "OrderIntent",
    "OrderIntentId",
    "AuditEvent",
    "AuditEventId",
    "AuditEventType",
    "AuthSession",
    "CredentialType",
    "Device",
    "DeviceStatus",
    "MFAMethod",
    "ROLE_PRIVILEGE_LEVEL",
    "SessionStatus",
    "Tenant",
    "TenantId",
    "TradingProfile",
    "User",
    "UserId",
    "UserRole",
    "can_manage_role",
]

__version__ = "0.1.0"
