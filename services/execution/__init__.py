"""Execution service for Kian Trading Intelligence.

Per AD-004: the Execution & Supervisor Agent coordinates authorized order
lifecycle, exchange adapter orchestration, and reconciliation. It is
prohibited from bypassing risk authorization.

Per Section 05.1: the mandatory execution pipeline is:
1. Validate market data.
2. Generate trade intent.
3. Verify tenant and session authorization.
4. Verify provider and compliance eligibility.
5. Reserve risk capacity.
6. Issue bounded risk authorization.
7. Persist the authorized order intent.
8. Submit through an approved exchange adapter.
9. Record acknowledgement or uncertain outcome.
10. Reconcile exchange execution.
11. Post confirmed financial effects.
12. Update audit and notifications.

Per E3 (Structure and Verification Separation): the concrete ExchangeSimulator
has been moved to the simulation/ package (outside the deployable services/ tree).
The ExecutionEngine depends on the ExchangeAdapter protocol, not the concrete
simulator. Import the simulator from simulation.exchange_simulator when needed
for testing or simulation mode.
"""

from contracts.exchange_adapter import ExchangeAdapter
from services.execution.engine import (
    ExecutionEngine,
    ExecutionError,
    OrderNotInValidStateException,
    RiskDeniedError,
    UnknownOutcomeUnresolvedError,
)

__all__ = [
    "ExchangeAdapter",
    "ExecutionEngine",
    "ExecutionError",
    "OrderNotInValidStateException",
    "RiskDeniedError",
    "UnknownOutcomeUnresolvedError",
]
