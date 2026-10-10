"""Shared contracts for Kian Trading Intelligence.

This package contains Pydantic models and enumerations shared across
backend services, agents, and API boundaries.

Architecture Decisions: AD-003 (Hybrid Low-Token Intelligence),
AD-004 (Four Agents + Risk Kernel), AD-014 (Deterministic Execution),
AD-021 (Shared Market Data).
"""

from contracts.enums import OperatingMode, OrderState, SessionState
from contracts.exchange import (
    ClientOrderId,
    ExchangeOrder,
    ExchangeOrderId,
    ExchangeSubmissionResult,
    FillResult,
    FillStatus,
    OrderSide,
    OrderType,
)
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
from contracts.indicators import (
    CandleSeries,
    IndicatorResult,
    exponential_moving_average,
    relative_strength_index,
    simple_moving_average,
    volatility,
)
from contracts.market_data import (
    Candle,
    DataStatus,
    EventId,
    FreshnessConfig,
    MarketDataEvent,
    MarketDataEventType,
    OrderBookLevel,
    OrderBookSnapshot,
    ProviderType,
    Symbol,
    Ticker,
    Timeframe,
    Trade,
)
from contracts.mode import OperatingModeConfig
from contracts.order import OrderIntent, OrderIntentId
from contracts.risk import (
    LEGAL_SESSION_TRANSITIONS,
    AuthorizationStatus,
    ReservationId,
    ReservationStatus,
    RiskAssessment,
    RiskAuthorization,
    RiskAuthorizationId,
    RiskPolicy,
    RiskPolicyId,
    RiskPolicyStatus,
    RiskReservation,
)
from contracts.trading import (
    LEGAL_SESSION_TRANSITIONS as TRADING_SESSION_TRANSITIONS,
)
from contracts.trading import (
    SessionId,
    TradingSession,
)

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
    # Phase 03 — Market Data
    "Candle",
    "CandleSeries",
    "DataStatus",
    "EventId",
    "FreshnessConfig",
    "IndicatorResult",
    "MarketDataEvent",
    "MarketDataEventType",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "ProviderType",
    "Symbol",
    "Timeframe",
    "Ticker",
    "Trade",
    "exponential_moving_average",
    "relative_strength_index",
    "simple_moving_average",
    "volatility",
    # Phase 04 — Risk Kernel and Trading Execution
    "AuthorizationStatus",
    "ClientOrderId",
    "ExchangeOrder",
    "ExchangeOrderId",
    "ExchangeSubmissionResult",
    "FillResult",
    "FillStatus",
    "LEGAL_SESSION_TRANSITIONS",
    "OrderSide",
    "OrderType",
    "ReservationId",
    "ReservationStatus",
    "RiskAssessment",
    "RiskAuthorization",
    "RiskAuthorizationId",
    "RiskPolicy",
    "RiskPolicyId",
    "RiskPolicyStatus",
    "RiskReservation",
    "SessionId",
    "TradingSession",
    "TRADING_SESSION_TRANSITIONS",
]

__version__ = "0.4.0"
