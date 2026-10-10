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
"""

from services.execution.engine import (
    ExecutionEngine,
    ExecutionError,
    OrderNotInValidStateException,
    RiskDeniedError,
    UnknownOutcomeUnresolvedError,
)
from services.execution.exchange_simulator import (
    DuplicateOrderError,
    ExchangeAdapterError,
    ExchangeNotConnectedError,
    ExchangeSimulator,
    OrderNotFoundError,
    ReconciliationRequired,
)

__all__ = [
    "DuplicateOrderError",
    "ExchangeAdapterError",
    "ExchangeNotConnectedError",
    "ExchangeSimulator",
    "ExecutionEngine",
    "ExecutionError",
    "OrderNotFoundError",
    "OrderNotInValidStateException",
    "ReconciliationRequired",
    "RiskDeniedError",
    "UnknownOutcomeUnresolvedError",
]
