"""Health and root API router for Kian Trading Intelligence.

Per AD-003: operating mode is always clearly identified.
Per Addendum A11: OpenAPI/Swagger documentation alignment.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from contracts import OperatingModeConfig
from services.core.version import __version__

router = APIRouter(tags=["Health"])

_mode_config = OperatingModeConfig()


@router.get("/health")
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


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    """Readiness check endpoint."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "service": "kian-trading-intelligence",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@router.get("/")
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
