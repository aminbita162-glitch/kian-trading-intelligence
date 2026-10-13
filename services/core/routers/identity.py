"""Identity and multi-tenant API router for Kian Trading Intelligence.

Per AD-002: tenants are the isolation boundary.
Per AD-010: failed attempts are tracked; accounts lock after max.
Per AD-026: sessions are revocable and tenant-scoped; MFA required for
privileged users; successful MFA grants step-up for sensitive operations.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from contracts.identity import MFAMethod, TenantId
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

router = APIRouter(tags=["Identity"])


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


# ── Endpoints ──


@router.post("/tenants", response_model=TenantResponse, status_code=201)
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


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
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


@router.post("/auth/login", response_model=LoginResponse)
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


@router.post("/auth/mfa/setup", response_model=MFASetupResponse)
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


@router.post("/auth/mfa/verify")
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


@router.post("/sessions/validate", response_model=SessionResponse)
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
