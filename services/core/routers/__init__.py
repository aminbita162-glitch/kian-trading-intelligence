"""API routers for Kian Trading Intelligence.

Per E3 (Structure and Verification Separation): the monolithic router
in services/core/app.py has been split into separate router modules,
each owning a single domain's endpoints. Each router is an APIRouter
that the app factory includes.

Routers:
- health: health, readiness, root endpoints
- identity: tenants, auth, MFA, sessions (Phase 02)
- market_data: market data endpoints (Phase 03)
- client: remote commands, notifications, incidents, onboarding (Phase 08)
- release: release engineering endpoints (Phase 10)
"""

from __future__ import annotations
