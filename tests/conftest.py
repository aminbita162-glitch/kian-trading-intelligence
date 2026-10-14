"""Shared pytest fixtures for the Kian Trading Intelligence test suite.

Ensures persistent stores (SQLAlchemy engines) are properly disposed after
each test to avoid ``ResourceWarning: unclosed database`` on Python 3.13+,
where ``filterwarnings = ["error"]`` turns resource warnings into test
failures.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from services.identity.database import reset_store


@pytest.fixture(autouse=True)
def clean_identity_state() -> Generator[None, None, None]:
    """Reset all identity-related state before and after each test.

    ``reset_store()`` delegates to ``reset_persistent_store()`` which
    disposes the old SQLAlchemy engine before creating a fresh one,
    ensuring SQLite connections are not leaked between tests.
    """
    reset_store()
    yield
    reset_store()


@pytest.fixture(autouse=True)
def clean_ledger_and_kernel_state() -> Generator[None, None, None]:
    """Dispose any PersistentLedger and PersistentRiskKernel engines.

    The persistent ledger and risk kernel modules track all live
    instances via class-level lists. This fixture ensures that any
    engines created by tests (that don't go through the singleton
    path) are disposed after each test to prevent ResourceWarning
    on Python 3.13+.
    """
    yield
    # Clean up after the test — dispose any lingering engines.
    try:
        from services.ledger.persistent_ledger import _close_all_ledger_instances

        _close_all_ledger_instances()
    except ImportError:
        pass
    try:
        from services.risk_kernel.persistent_kernel import (
            _close_all_kernel_instances,
        )

        _close_all_kernel_instances()
    except ImportError:
        pass
