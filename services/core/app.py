"""Kian Trading Intelligence — Core Backend Service.

Architecture Decision AD-031: Python/FastAPI for the core backend.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from contracts import OperatingMode, OperatingModeConfig

__version__ = "0.1.0"

app = FastAPI(
    title="Kian Trading Intelligence API",
    description=(
        "Secure, auditable, cost-aware cryptocurrency trading and mining "
        "intelligence platform. Phase 01 — Engineering Foundation."
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
