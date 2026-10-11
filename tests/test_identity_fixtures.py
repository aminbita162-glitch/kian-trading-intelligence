"""Test fixtures for Phase 02 identity and security tests.

The autouse fixture in ``tests/conftest.py`` now handles resetting all
identity-related state (including disposing SQLAlchemy engines) before
and after each test.  This module kept for backward compatibility —
its fixture was consolidated into ``conftest.py`` to ensure engine
cleanup runs for every test module, not just those that import this.
"""

from collections.abc import Generator

import pytest

from services.identity.auth import reset_passwords
from services.identity.credential_vault import reset_vault
from services.identity.database import reset_store


@pytest.fixture(autouse=True)
def clean_identity_state() -> Generator[None, None, None]:
    """Reset all identity-related state before and after each test.

    ``reset_store()`` disposes the old SQLAlchemy engine and creates a
    fresh one, ensuring SQLite connections are not leaked between tests
    (Python 3.13 ``ResourceWarning`` fix).
    """
    reset_store()
    reset_passwords()
    reset_vault()
    yield
    reset_store()
    reset_passwords()
    reset_vault()
