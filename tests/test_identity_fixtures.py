"""Test fixtures for Phase 02 identity and security tests.

Provides a clean IdentityStore, password store, and credential vault
reset for each test to avoid state leakage.
"""

from collections.abc import Generator

import pytest

from services.identity.auth import reset_passwords
from services.identity.credential_vault import reset_vault
from services.identity.database import reset_store


@pytest.fixture(autouse=True)
def clean_identity_state() -> Generator[None, None, None]:
    """Reset all identity-related state before each test."""
    reset_store()
    reset_passwords()
    reset_vault()
    yield
    # Cleanup after test as well
    reset_store()
    reset_passwords()
    reset_vault()
