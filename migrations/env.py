"""Alembic environment script for Kian Trading Intelligence.

NOTE: Alembic is NOT installed as a dependency. This environment script
is provided for future use. The lightweight migration framework in
services/identity/migrations.py is used instead.
"""

from __future__ import annotations

from typing import Any

try:
    from alembic import context  # type: ignore[import-not-found]
except ImportError:
    context = None  # type: ignore[assignment]

try:
    from services.identity.persistence import Base
except ImportError:
    Base = None  # type: ignore[assignment]


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    if context is None:
        return
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    if context is None:
        return
    from sqlalchemy import engine_from_config  # type: ignore[import-not-found]

    config = context.config
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        return
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
