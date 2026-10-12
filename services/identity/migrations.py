"""Lightweight migration framework for the identity database.

Architecture Decisions: AD-024 (Progressive Delivery), AD-031 (PostgreSQL).

Provides a simple versioned migration system using raw SQL, avoiding
the need for Alembic as a dependency. Each migration has a version,
description, up_sql, and down_sql. Migrations are applied in order and
tracked in the ``schema_version`` table.

The existing :func:`services.identity.persistence._ensure_schema` now
delegates to :func:`run_migrations` from this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class Migration:
    """A single database migration."""

    version: int
    description: str
    up_sql: str
    down_sql: str


def create_migration(
    version: int,
    description: str,
    up_sql: str,
    down_sql: str,
) -> Migration:
    """Factory for creating a Migration instance."""
    return Migration(
        version=version,
        description=description,
        up_sql=up_sql,
        down_sql=down_sql,
    )


# ── Migrations ──

_MIGRATION_V1_UP = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    mfa_enabled BOOLEAN DEFAULT FALSE,
    mfa_method VARCHAR(50),
    mfa_secret VARCHAR(255),
    failed_login_count INTEGER DEFAULT 0,
    locked_until VARCHAR(40),
    created_at VARCHAR(40) NOT NULL,
    password_hash VARCHAR(255),
    password_salt VARCHAR(255)
);
CREATE TABLE IF NOT EXISTS profiles (
    profile_id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'en',
    base_currency VARCHAR(20) DEFAULT 'USDT',
    risk_tolerance VARCHAR(50) DEFAULT 'moderate',
    is_active BOOLEAN DEFAULT TRUE,
    created_at VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    device_id VARCHAR(36),
    status VARCHAR(50) NOT NULL,
    step_up_until VARCHAR(40),
    expires_at VARCHAR(40) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    last_activity VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    fingerprint VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    trusted_at VARCHAR(40),
    last_seen VARCHAR(40) NOT NULL,
    created_at VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    event_id VARCHAR(36) PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    actor_user_id VARCHAR(36),
    timestamp VARCHAR(40) NOT NULL,
    detail VARCHAR(1000) NOT NULL,
    metadata_json VARCHAR(4000) DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at VARCHAR(40) NOT NULL
);
"""

_MIGRATION_V1_DOWN = """
DROP TABLE IF EXISTS schema_version;
DROP TABLE IF EXISTS audit_events;
DROP TABLE IF EXISTS devices;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS profiles;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS tenants;
"""

_MIGRATION_V2_UP = """
-- Add MFA columns if they don't already exist (idempotent).
-- SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN,
-- so we use a conditional approach.
"""

_MIGRATION_V2_DOWN = ""
"-- No-op: columns are part of the initial schema in v1."


MIGRATIONS: list[Migration] = [
    create_migration(
        version=1,
        description="Initial identity schema — tenants, users, profiles, "
        "sessions, devices, audit_events, schema_version",
        up_sql=_MIGRATION_V1_UP,
        down_sql=_MIGRATION_V1_DOWN,
    ),
    create_migration(
        version=2,
        description="Add mfa_secret and mfa_enabled columns (idempotent)",
        up_sql=_MIGRATION_V2_UP,
        down_sql=_MIGRATION_V2_DOWN,
    ),
]


def get_current_version(engine: Engine | Any) -> int:
    """Return the highest applied migration version, or 0 if none."""
    with Session(engine) as session:
        try:
            result = session.execute(text("SELECT MAX(version) FROM schema_version"))
            row = result.fetchone()
            if row is not None and row[0] is not None:
                return int(row[0])
        except Exception:
            # Table doesn't exist yet
            return 0
    return 0


def run_migrations(engine: Engine | Any) -> int:
    """Apply all pending migrations to *engine*.

    Returns the highest applied version.
    """
    current = get_current_version(engine)
    for migration in MIGRATIONS:
        if migration.version <= current:
            continue
        with Session(engine) as session:
            if migration.up_sql.strip():
                for raw_stmt in migration.up_sql.strip().split(";"):
                    stmt = raw_stmt.strip()
                    if stmt:
                        session.execute(text(stmt))
            session.execute(
                text(
                    "INSERT INTO schema_version (version, applied_at) "
                    "VALUES (:version, :applied_at)"
                ),
                {
                    "version": migration.version,
                    "applied_at": datetime.now(UTC).isoformat(),
                },
            )
            session.commit()
    return MIGRATIONS[-1].version if MIGRATIONS else 0
