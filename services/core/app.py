"""Kian Trading Intelligence — Core Backend Service.

Per E3 (Structure and Verification Separation): the monolithic router
has been split into separate domain-specific router modules under
services/core/routers/. Each router owns a single domain's endpoints.
Simulators and readiness generators have been moved to the simulation/
package (outside the deployable image).

Per AD-031: Python/FastAPI for the core backend.
Per AD-003: operating mode is always clearly identified.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from contracts import OperatingMode, OperatingModeConfig
from services.core.routers.client import router as client_router
from services.core.routers.health import router as health_router
from services.core.routers.identity import router as identity_router
from services.core.routers.market_data import router as market_data_router
from services.core.routers.release import router as release_router
from services.core.version import __version__
from services.security import SecurityService

# ── Phase 09 — Security Service (production) ──
_security_service = SecurityService()

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


app = FastAPI(
    title="Kian Trading Intelligence API",
    description=(
        "Secure, auditable, cost-aware cryptocurrency trading and mining "
        "intelligence platform. E3 — Structure and Verification Separation."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Include all domain routers
app.include_router(health_router)
app.include_router(identity_router)
app.include_router(market_data_router)
app.include_router(client_router)
app.include_router(release_router)
