"""Shared pytest fixtures for the Kian Trading Intelligence test suite.

Ensures persistent identity stores (SQLAlchemy engines) are properly
disposed after each test to avoid ``ResourceWarning: unclosed database``
on Python 3.13+, where ``filterwarnings = ["error"]`` turns resource
warnings into test failures.
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
