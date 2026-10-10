"""Kian Trading Intelligence — Core Backend Service.

Architecture Decision AD-031: Python/FastAPI for the core backend.
Phase 02: Identity and multi-tenant security endpoints.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from contracts import OperatingMode, OperatingModeConfig
from contracts.identity import MFAMethod, TenantId
from contracts.market_data import (
    Symbol,
    Timeframe,
)
from services.client import (
    AuthAssurance,
    EmergencyStopRequest,
    EmergencyStopResponse,
    Incident,
    IncidentCreateRequest,
    IncidentService,
    Notification,
    NotificationCreateRequest,
    NotificationPreferences,
    NotificationService,
    OnboardingStep,
    RemoteCommand,
    RemoteCommandRequest,
    RemoteCommandResponse,
    RemoteCommandService,
    RemoteCommandStatus,
    RemoteCommandType,
    SimulatedWorkflowResult,
    next_onboarding_step,
    run_simulated_workflow,
)
from services.identity.auth import (
    AccountInactiveError,
    AccountLockedError,
    AuthenticationError,
    authenticate,
)
from services.identity.database import get_store
from services.identity.mfa import MFAError, enable_mfa, verify_mfa
from services.identity.session import validate_session
from services.identity.tenant import (
    TenantNotFoundError,
    create_tenant,
    get_tenant,
)
from services.market_data.processor import EventProcessor
from services.market_data.simulated import SimulatedMarketDataProvider
from services.market_data.storage import HistoricalStorage
from services.security import SecurityService

# ── Phase 08 — Client Application Services ──
_remote_command_service = RemoteCommandService()
_notification_service = NotificationService()
_incident_service = IncidentService()

# ── Phase 09 — Security, Resilience, and Scale ──
_security_service = SecurityService()

__version__ = "0.9.0"

app = FastAPI(
    title="Kian Trading Intelligence API",
    description=(
        "Secure, auditable, cost-aware cryptocurrency trading and mining "
        "intelligence platform. Phase 09 — Security, Resilience, and Scale."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Operating Mode Guard ──
_mode_config = OperatingModeConfig()


def _get_env_mode() -> OperatingMode:
    """Read operating mode from environment, defaulting to SIMULATION."""
    env_mode = os.environ.get("KTI_OPERATING_MODE", "simulation").lower()
    try:
        return OperatingMode(env_mode)
    except ValueError:
        return OperatingMode.SIMULATION


# Initialize mode — LIVE requires explicit env var + authorization
_env_mode = _get_env_mode()
if _env_mode is OperatingMode.LIVE:
    # LIVE mode is never auto-enabled; requires explicit code authorization
    _mode_config.set_mode(OperatingMode.SIMULATION)
else:
    _mode_config.set_mode(_env_mode)


# ── Request/Response Models ──


class TenantCreateRequest(BaseModel):
    """Request to create a new tenant."""

    name: str = Field(..., min_length=1, max_length=200)


class TenantResponse(BaseModel):
    """Tenant response model."""

    tenant_id: str
    name: str
    is_active: bool


class LoginRequest(BaseModel):
    """Login request model."""

    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    device_fingerprint: str | None = None


class LoginResponse(BaseModel):
    """Login response model."""

    session_id: str
    user_id: str
    tenant_id: str
    email: str
    role: str
    mfa_required: bool


class MFAVerifyRequest(BaseModel):
    """MFA verification request."""

    session_id: str
    code: str = Field(..., min_length=6, max_length=6)


class MFASetupRequest(BaseModel):
    """MFA setup request."""

    session_id: str
    method: str = Field(default="totp")


class MFASetupResponse(BaseModel):
    """MFA setup response with secret."""

    secret: str
    method: str


class SessionValidateRequest(BaseModel):
    """Session validation request."""

    session_id: str


class SessionResponse(BaseModel):
    """Session response model."""

    session_id: str
    user_id: str
    tenant_id: str
    status: str
    has_step_up: bool
    is_expired: bool


# ── Health Endpoints ──


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint.

    Returns service status and active operating mode.
    The operating mode is always clearly identified (AD-003, Section 01.3).
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "kian-trading-intelligence",
            "version": __version__,
            "operating_mode": _mode_config.mode.value,
            "is_live": _mode_config.is_live,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@app.get("/health/ready")
async def readiness() -> JSONResponse:
    """Readiness check endpoint."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "service": "kian-trading-intelligence",
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with API metadata."""
    return {
        "name": "Kian Trading Intelligence API",
        "version": __version__,
        "operating_mode": _mode_config.mode.value,
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }


# ── Identity Endpoints (Phase 02) ──


@app.post("/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant_endpoint(req: TenantCreateRequest) -> TenantResponse:
    """Create a new tenant.

    Per AD-002: tenants are the isolation boundary.
    """
    tenant = create_tenant(name=req.name)
    return TenantResponse(
        tenant_id=str(tenant.tenant_id),
        name=tenant.name,
        is_active=tenant.is_active,
    )


@app.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant_endpoint(tenant_id: str) -> TenantResponse:
    """Get a tenant by ID."""
    try:
        tid = TenantId(value=UUID(tenant_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format",
        ) from None

    try:
        tenant = get_tenant(tid)
    except TenantNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        ) from None

    return TenantResponse(
        tenant_id=str(tenant.tenant_id),
        name=tenant.name,
        is_active=tenant.is_active,
    )


@app.post("/auth/login", response_model=LoginResponse)
async def login_endpoint(req: LoginRequest) -> LoginResponse:
    """Authenticate a user and create a session.

    Per AD-010: failed attempts are tracked; accounts lock after max.
    Per AD-026: sessions are revocable and tenant-scoped.
    """
    try:
        tid = TenantId(value=UUID(req.tenant_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format",
        ) from None

    try:
        user, session = authenticate(
            tenant_id=tid,
            email=req.email,
            password=req.password,
            device_fingerprint=req.device_fingerprint,
        )
    except AccountLockedError:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is locked due to failed attempts",
        ) from None
    except AccountInactiveError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        ) from None
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from None

    return LoginResponse(
        session_id=str(session.session_id),
        user_id=str(user.user_id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        role=user.role.value,
        mfa_required=user.mfa_enabled,
    )


@app.post("/auth/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup_endpoint(req: MFASetupRequest) -> MFASetupResponse:
    """Set up MFA for a user.

    Per AD-026: MFA is required for privileged users.
    """
    try:
        session = validate_session(req.session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from None

    user = get_store().get_user(session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    method = MFAMethod(req.method)
    secret = enable_mfa(user, method)
    return MFASetupResponse(secret=secret, method=method.value)


@app.post("/auth/mfa/verify")
async def mfa_verify_endpoint(req: MFAVerifyRequest) -> dict[str, bool]:
    """Verify an MFA code and grant step-up authorization.

    Per AD-026: successful MFA grants step-up for sensitive operations.
    """
    try:
        session = validate_session(req.session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from None

    user = get_store().get_user(session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    try:
        verify_mfa(session, user, req.code)
        return {"verified": True}
    except MFAError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA verification failed",
        ) from None


@app.post("/sessions/validate", response_model=SessionResponse)
async def validate_session_endpoint(req: SessionValidateRequest) -> SessionResponse:
    """Validate a session and return its status.

    Per AD-026: sessions are revocable and expire automatically.
    """
    try:
        session = validate_session(req.session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from None

    return SessionResponse(
        session_id=str(session.session_id),
        user_id=str(session.user_id),
        tenant_id=str(session.tenant_id),
        status=session.status.value,
        has_step_up=session.has_step_up,
        is_expired=session.is_expired,
    )


# ── Market Data Endpoints (Phase 03) ──

# Singletons for Phase 03 — in-memory (production needs PostgreSQL + Redis)
_market_storage = HistoricalStorage()
_market_provider = SimulatedMarketDataProvider()
_market_processor = EventProcessor(storage=_market_storage)

# Provider is connected in SIMULATION mode (no real exchange)
if not _mode_config.is_live:
    import asyncio as _asyncio

    _loop = _asyncio.new_event_loop()
    _loop.run_until_complete(_market_provider.connect())
    _loop.close()


class TickerResponse(BaseModel):
    """Market data ticker response."""

    symbol: str
    last_price: str
    bid: str
    ask: str
    high_24h: str
    low_24h: str
    volume_24h: str
    timestamp: str


class OrderBookResponse(BaseModel):
    """Order book snapshot response."""

    symbol: str
    bids: list[list[str]]
    asks: list[list[str]]
    timestamp: str
    sequence: int


class CandleResponse(BaseModel):
    """OHLCV candle response."""

    symbol: str
    timeframe: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    open_time: str
    close_time: str


class MarketDataHealthResponse(BaseModel):
    """Market data service health response."""

    provider: str
    connected: bool
    rate_limit_remaining: int
    stored_events: int
    freshness_max_age: str


@app.get("/market-data/health", response_model=MarketDataHealthResponse)
async def market_data_health() -> MarketDataHealthResponse:
    """Market data service health and status.

    Per AD-021: market data infrastructure health.
    Per AD-003: operating mode is always identified.
    """
    return MarketDataHealthResponse(
        provider=_market_provider.provider_type.value,
        connected=_market_provider.connection.connected,
        rate_limit_remaining=_market_provider.rate_limiter.remaining(),
        stored_events=_market_storage.count,
        freshness_max_age=f"{_market_processor.freshness.max_age}",
    )


@app.get("/market-data/ticker/{symbol_pair:path}", response_model=TickerResponse)
async def get_ticker_endpoint(symbol_pair: str) -> TickerResponse:
    """Get the current ticker for a symbol pair.

    Per AD-021: normalized market data.
    Per Section 08.1: approved provider adapters with normalized schemas.
    """
    try:
        symbol = Symbol.parse(symbol_pair)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid symbol format: {symbol_pair}. Expected 'BASE/QUOTE'.",
        ) from None

    try:
        ticker = await _market_provider.get_ticker(symbol)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market data provider error: {exc}",
        ) from None

    return TickerResponse(
        symbol=ticker.symbol.pair,
        last_price=ticker.last_price,
        bid=ticker.bid,
        ask=ticker.ask,
        high_24h=ticker.high_24h,
        low_24h=ticker.low_24h,
        volume_24h=ticker.volume_24h,
        timestamp=ticker.timestamp.isoformat(),
    )


@app.get("/market-data/orderbook/{symbol_pair:path}", response_model=OrderBookResponse)
async def get_orderbook_endpoint(
    symbol_pair: str,
    depth: int = 10,
) -> OrderBookResponse:
    """Get the current order book snapshot for a symbol pair.

    Per Section 08.1: order book with ordering controls.
    """
    try:
        symbol = Symbol.parse(symbol_pair)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid symbol format: {symbol_pair}. Expected 'BASE/QUOTE'.",
        ) from None

    try:
        book = await _market_provider.get_order_book(symbol, depth=depth)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market data provider error: {exc}",
        ) from None

    return OrderBookResponse(
        symbol=book.symbol.pair,
        bids=[[lvl.price, lvl.amount] for lvl in book.bids],
        asks=[[lvl.price, lvl.amount] for lvl in book.asks],
        timestamp=book.timestamp.isoformat(),
        sequence=book.sequence,
    )


@app.get("/market-data/candles/{symbol_pair:path}", response_model=list[CandleResponse])
async def get_candles_endpoint(
    symbol_pair: str,
    timeframe: str = "1m",
    limit: int = 100,
) -> list[CandleResponse]:
    """Get historical candles for a symbol pair.

    Per Section 08.1: historical storage and deterministic replay.
    Per AD-003: deterministic, no LLM dependency.
    """
    try:
        symbol = Symbol.parse(symbol_pair)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid symbol format: {symbol_pair}. Expected 'BASE/QUOTE'.",
        ) from None

    try:
        tf = Timeframe(timeframe)
    except ValueError:
        supported = ", ".join(t.value for t in Timeframe)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timeframe: {timeframe}. Supported: {supported}",
        ) from None

    MAX_CANDLE_LIMIT = 1000

    if limit < 1 or limit > MAX_CANDLE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 1000.",
        )

    try:
        candles = await _market_provider.get_candles(symbol, tf, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market data provider error: {exc}",
        ) from None

    return [
        CandleResponse(
            symbol=c.symbol.pair,
            timeframe=c.timeframe.value,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            open_time=c.open_time.isoformat(),
            close_time=c.close_time.isoformat(),
        )
        for c in candles
    ]


# ── Phase 08 — Client Application Endpoints ──


@app.post("/remote-commands", response_model=RemoteCommandResponse)
async def issue_remote_command(
    req: RemoteCommandRequest,
) -> RemoteCommandResponse:
    """Issue a remote command (AD-027, Section 10.4).

    Per AD-027: remote commands require typed action contracts, valid
    authorization, expiry, idempotency, and auditable outcomes.
    Per Section 05.6: emergency stop uses a deterministic path.
    """
    has_step_up = req.authentication_assurance is AuthAssurance.STEP_UP
    cmd = _remote_command_service.execute_command(req, has_step_up)
    return RemoteCommandResponse(
        command_id=cmd.command_id,
        status=cmd.status,
        message=cmd.error or cmd.result or "Command processed",
        executed_at=cmd.created_at,
    )


@app.post("/remote-commands/emergency-stop", response_model=EmergencyStopResponse)
async def emergency_stop(req: EmergencyStopRequest) -> EmergencyStopResponse:
    """Trigger an emergency stop (Section 05.6).

    Per Section 05.6: blocks new exposure-increasing orders; prevents
    automatic trading restart; uses a deterministic path independent of
    LLM processing.
    """
    cmd_req = RemoteCommandRequest(
        command_type=RemoteCommandType.EMERGENCY_STOP,
        tenant_id=req.tenant_id,
        user_id=req.user_id,
        profile_id="emergency-stop",
        target_resource="all-sessions",
        operation="emergency_stop",
        idempotency_key=req.idempotency_key,
        authentication_assurance=req.authentication_assurance,
    )
    cmd = _remote_command_service.execute_command(
        cmd_req,
        req.authentication_assurance is AuthAssurance.STEP_UP,
    )
    accepted = cmd.status is RemoteCommandStatus.COMPLETED
    return EmergencyStopResponse(
        accepted=accepted,
        timestamp=cmd.created_at,
        message=cmd.result or cmd.error or "Emergency stop processed",
        operating_mode=_mode_config.mode.value,
        pending_orders_blocked=accepted,
    )


@app.get("/remote-commands/{tenant_id}", response_model=list[RemoteCommand])
async def get_command_history(
    tenant_id: str,
    limit: int = 50,
) -> list[RemoteCommand]:
    """Get remote command history for a tenant (AD-027 audit trail)."""
    return _remote_command_service.get_command_history(tenant_id, limit=limit)


@app.post("/notifications", response_model=Notification)
async def create_notification_endpoint(
    req: NotificationCreateRequest,
) -> Notification:
    """Create a notification in the unified hub (AD-009)."""
    notif = _notification_service.create_notification(req)
    if notif is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Notification suppressed by user preferences",
        )
    return notif


@app.get("/notifications/{tenant_id}/{user_id}", response_model=list[Notification])
async def get_notifications_endpoint(
    tenant_id: str,
    user_id: str,
    limit: int = 50,
) -> list[Notification]:
    """Get notifications for a user (AD-009)."""
    return _notification_service.get_notifications(tenant_id, user_id, limit=limit)


@app.patch("/notifications/{notification_id}/read", response_model=Notification)
async def mark_notification_read(notification_id: str) -> Notification:
    """Mark a notification as read."""
    if not _notification_service.mark_as_read(notification_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    # Re-fetch — the service returns a bool, not the object
    notifs = [
        n
        for n in _notification_service.get_notifications(
            "any",
            "any",
            limit=10000,
        )
        if n.notification_id == notification_id
    ]
    if not notifs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found after update",
        )
    return notifs[0]


@app.put(
    "/notifications/preferences/{tenant_id}/{user_id}",
    response_model=NotificationPreferences,
)
async def update_notification_preferences(
    tenant_id: str,
    user_id: str,
    prefs: NotificationPreferences,
) -> NotificationPreferences:
    """Update notification preferences for a user (AD-009)."""
    prefs = prefs.model_copy(update={"tenant_id": tenant_id, "user_id": user_id})
    return _notification_service.update_preferences(prefs)


@app.get("/incidents/{tenant_id}", response_model=list[Incident])
async def get_incidents_endpoint(
    tenant_id: str,
    limit: int = 50,
) -> list[Incident]:
    """Get incidents for a tenant (AD-017)."""
    return _incident_service.get_incidents(tenant_id, limit=limit)


@app.post("/incidents", response_model=Incident, status_code=201)
async def create_incident_endpoint(
    req: IncidentCreateRequest,
) -> Incident:
    """Create a new incident (AD-017)."""
    return _incident_service.create_incident(req)


@app.post("/incidents/{incident_id}/resolve", response_model=Incident)
async def resolve_incident_endpoint(
    incident_id: str,
    tenant_id: str,
) -> Incident:
    """Resolve an incident. Per AD-017: requires human authorization."""
    if not _incident_service.resolve_incident(incident_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    incidents = _incident_service.get_incidents(tenant_id, limit=10000)
    for inc in incidents:
        if inc.incident_id == incident_id:
            return inc
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Incident not found after resolution",
    )


@app.get("/onboarding/next-step")
async def get_next_onboarding_step(current: str) -> dict[str, str | None]:
    """Get the next onboarding step (deliverable 3)."""
    try:
        step = OnboardingStep(current)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid onboarding step: {current}",
        ) from None
    nxt = next_onboarding_step(step)
    return {
        "current": current,
        "next": nxt.value if nxt else None,
    }


@app.post("/workflows/simulated", response_model=SimulatedWorkflowResult)
async def run_simulated_workflow_endpoint(
    tenant_id: str,
) -> SimulatedWorkflowResult:
    """Run a complete end-to-end simulated workflow (deliverable 12).

    Per Section 17 Phase 08 deliverable 12: end-to-end simulated workflows
    exercising all dashboard components, remote commands, notifications,
    and incident tracking in simulation mode.
    """
    return run_simulated_workflow(
        tenant_id=tenant_id,
        notification_service=_notification_service,
    )
