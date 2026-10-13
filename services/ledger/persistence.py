"""Persistent financial ledger store for Kian Trading Intelligence (E2 — Durable Core).

Architecture Decisions: AD-018 (durable, auditable financial records),
AD-031 (PostgreSQL for durable records), AD-024 (progressive delivery).

Replaces the in-memory ``FinancialLedger`` state with a SQLAlchemy-backed
persistent store that supports PostgreSQL (production) and SQLite
(in-process test / dev).  Key properties:

- **Balanced journals** — a DB CHECK constraint enforces ``debit_total =
  credit_total`` on every journal entry row.
- **Unique idempotency** — a UNIQUE constraint on ``idempotency_key``
  prevents duplicate postings at the database level.
- **Append-only** — journal entries and audit rows are INSERT-only;
  UPDATE and DELETE are rejected by a trigger (PostgreSQL) or by
  application-level enforcement (SQLite).
- **Row-Level Security** — every tenant-scoped table has an RLS policy
  restricting access to the caller's tenant (PostgreSQL only).
- **Transactional integrity** — all mutations occur within a single
  ``Session.begin()`` transaction; partial failures roll back.
- **Crash safety** — a crash at a transaction boundary leaves the
  database in a consistent state: either all changes are committed or
  none are.
- **No duplicate effects on replay** — idempotency keys and fill IDs
  have UNIQUE constraints; replaying the same event is a no-op.

The in-memory ``FinancialLedger`` remains available for dev/test via
``KTI_USE_PERSISTENT_STORE=false``; the default is the persistent store.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
)


class LedgerPersistenceError(Exception):
    """Raised when ledger persistence operations fail."""


class LedgerConfigurationError(LedgerPersistenceError):
    """Raised when the ledger persistence layer is misconfigured (fail-closed)."""


# ── Database URL resolution ──


def _resolve_db_url() -> str:
    """Resolve the database URL from the environment (fail-closed in prod)."""
    url = os.environ.get("KTI_DATABASE_URL", "")
    if _is_production():
        if not url:
            raise LedgerConfigurationError(
                "KTI_DATABASE_URL is not set. In production, a PostgreSQL "
                "connection URL is required."
            )
        if not url.startswith("postgresql"):
            raise LedgerConfigurationError(
                "KTI_DATABASE_URL must be a PostgreSQL URL in production."
            )
        return url
    if not url:
        return "sqlite:///:memory:"
    return url


def _is_production() -> bool:
    return os.environ.get("KTI_ENVIRONMENT", "").lower() == "production"


# ── SQLAlchemy models ──


class LedgerBase(DeclarativeBase):
    """Declarative base for all ledger tables."""


class FinancialAccountRow(LedgerBase):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "asset", name="uq_ledger_accounts_tenant_asset"),
        CheckConstraint("CAST(balance AS NUMERIC) >= 0", name="ck_ledger_accounts_balance_nonneg"),
        CheckConstraint(
            "CAST(reserved_balance AS NUMERIC) >= 0",
            name="ck_ledger_accounts_reserved_nonneg",
        ),
    )

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    account_type: Mapped[str] = mapped_column(String(50))
    asset: Mapped[str] = mapped_column(String(50))
    balance: Mapped[str] = mapped_column(String(40), default="0")
    reserved_balance: Mapped[str] = mapped_column(String(40), default="0")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class JournalEntryRow(LedgerBase):
    """Journal entry — append-only (INSERT, no UPDATE/DELETE on posted rows)."""

    __tablename__ = "ledger_journal_entries"
    __table_args__ = (
        # DB-enforced invariant: debits must equal credits.
        CheckConstraint("debit_total = credit_total", name="ck_journal_balanced"),
        # Unique idempotency key prevents duplicate postings at the DB level.
        UniqueConstraint(
            "idempotency_key",
            name="uq_journal_idempotency",
        ),
    )

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    entry_type: Mapped[str] = mapped_column(String(50))
    reference: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    debit_total: Mapped[str] = mapped_column(String(40))
    credit_total: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40))
    posted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class JournalLineRow(LedgerBase):
    __tablename__ = "ledger_journal_lines"
    __table_args__ = (
        CheckConstraint("CAST(amount AS NUMERIC) > 0", name="ck_journal_line_amount_positive"),
        CheckConstraint("CAST(value AS NUMERIC) > 0", name="ck_journal_line_value_positive"),
    )

    line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ledger_journal_entries.entry_id", ondelete="CASCADE"),
        index=True,
    )
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    side: Mapped[str] = mapped_column(String(10))
    amount: Mapped[str] = mapped_column(String(40))
    asset: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(String(40))


class IdempotencyKeyRow(LedgerBase):
    __tablename__ = "ledger_idempotency_keys"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_idempotency_key"),)

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40))


class FillMappingRow(LedgerBase):
    __tablename__ = "ledger_fill_mappings"
    __table_args__ = (UniqueConstraint("fill_id", name="uq_fill_id"),)

    fill_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    entry_ids: Mapped[str] = mapped_column(Text)
    asset_acquired: Mapped[str] = mapped_column(String(50))
    asset_cost: Mapped[str] = mapped_column(String(50))
    quantity: Mapped[str] = mapped_column(String(40))
    price: Mapped[str] = mapped_column(String(40))
    fee: Mapped[str] = mapped_column(String(40))
    fee_asset: Mapped[str] = mapped_column(String(50))
    realized_pnl: Mapped[str] = mapped_column(String(40), default="0")
    mapped_at: Mapped[str] = mapped_column(String(40))


class ProfitThresholdRow(LedgerBase):
    __tablename__ = "ledger_profit_thresholds"

    threshold_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    threshold_type: Mapped[str] = mapped_column(String(50))
    asset: Mapped[str] = mapped_column(String(50))
    threshold_value: Mapped[str] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40))


class ProfitReservationRow(LedgerBase):
    __tablename__ = "ledger_profit_reservations"

    reservation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    asset: Mapped[str] = mapped_column(String(50))
    reserved_amount: Mapped[str] = mapped_column(String(40))
    threshold_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[str] = mapped_column(String(40))
    released_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class WithdrawalRow(LedgerBase):
    __tablename__ = "ledger_withdrawals"

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    asset: Mapped[str] = mapped_column(String(50))
    amount: Mapped[str] = mapped_column(String(40))
    destination_address: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[str] = mapped_column(String(40))
    approved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    submitted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    provider_tx_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ReconciliationRow(LedgerBase):
    __tablename__ = "ledger_reconciliations"

    reconciliation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    asset: Mapped[str] = mapped_column(String(50))
    ledger_balance: Mapped[str] = mapped_column(String(40))
    exchange_balance: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(50), default="matched")
    created_at: Mapped[str] = mapped_column(String(40))
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolution_notes: Mapped[str] = mapped_column(Text, default="")


class LedgerPositionRow(LedgerBase):
    """Position tracking — cost basis and quantity per tenant+symbol."""

    __tablename__ = "ledger_positions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "symbol", name="uq_ledger_positions_tenant_symbol"),
    )

    position_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    symbol: Mapped[str] = mapped_column(String(50))
    quantity: Mapped[str] = mapped_column(String(40), default="0")
    cost_basis: Mapped[str] = mapped_column(String(40), default="0")


class RealizedPnlRow(LedgerBase):
    """Realized P&L running total per tenant."""

    __tablename__ = "ledger_realized_pnl"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_realized_pnl_tenant"),)

    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    total: Mapped[str] = mapped_column(String(40), default="0")


class OutboxEventRow(LedgerBase):
    """Transactional outbox — events written in the same DB transaction.

    A separate process (or test) polls the outbox and delivers events.
    ``processed_at`` is NULL until the event has been successfully
    delivered; setting it marks the event as consumed.

    Per E2 scope: transactional outbox for reliable event delivery without
    distributed transactions.
    """

    __tablename__ = "ledger_outbox"
    __table_args__ = (CheckConstraint("sequence_num > 0", name="ck_outbox_seq_positive"),)

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence_num: Mapped[int] = mapped_column(Integer, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String(40))
    processed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class InboxMessageRow(LedgerBase):
    """Transactional inbox — idempotent message processing.

    Incoming messages are stored with a unique ``message_id``. If the
    same message arrives again, it is deduplicated by the UNIQUE
    constraint. ``processed_at`` marks the message as handled.

    Per E2 scope: transactional inbox for idempotent message processing.
    """

    __tablename__ = "ledger_inbox"
    __table_args__ = (UniqueConstraint("message_id", name="uq_inbox_message_id"),)

    inbox_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    received_at: Mapped[str] = mapped_column(String(40))
    processed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class LedgerSchemaVersionRow(LedgerBase):
    __tablename__ = "ledger_schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(500))
    applied_at: Mapped[str] = mapped_column(String(40))


# ── Helpers ──


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _now_str() -> str:
    return datetime.now(UTC).isoformat()


# ── Migrations (versioned, up/down) ──

LEDGER_MIGRATIONS: list[tuple[int, str, str, str]] = [
    (
        1,
        "Initial ledger schema — accounts, journal entries, lines, "
        "idempotency keys, fill mappings, profit thresholds, profit "
        "reservations, withdrawals, reconciliations, positions, "
        "realized P&L, outbox, inbox, schema_version",
        "",  # Tables created via create_all()
        "",  # Tables dropped via drop_all()
    ),
    (
        2,
        "Add RLS policies for tenant isolation (PostgreSQL only)",
        "",  # Applied via _apply_rls_policies()
        "",  # Reverted via _revert_rls_policies()
    ),
    (
        3,
        "Add append-only trigger for journal entries (PostgreSQL only)",
        "",  # Applied via _apply_append_only_trigger()
        "",  # Reverted via _revert_append_only_trigger()
    ),
]

RLS_MIGRATION_VERSION = 2
APPEND_ONLY_MIGRATION_VERSION = 3

LEDGER_CURRENT_VERSION = len(LEDGER_MIGRATIONS)


def _is_postgres(engine: Any) -> bool:
    """Check if the engine is connected to PostgreSQL."""
    return bool(engine.dialect.name == "postgresql")


def _apply_rls_policies(session: Session) -> None:
    """Apply Row-Level Security policies for tenant isolation.

    Per E2 scope: RLS (Row-Level Security) for tenant isolation at the
    database level. Only applicable to PostgreSQL.
    """
    # Only tables that have a tenant_id column can have an RLS policy
    # referencing it. ledger_journal_lines, ledger_idempotency_keys, and
    # ledger_fill_mappings do NOT have tenant_id (they are linked via
    # entry_id / idempotency_key / fill_id to parent rows that do).
    tenant_tables = [
        "ledger_accounts",
        "ledger_journal_entries",
        "ledger_profit_thresholds",
        "ledger_profit_reservations",
        "ledger_withdrawals",
        "ledger_reconciliations",
        "ledger_positions",
        "ledger_realized_pnl",
        "ledger_outbox",
        "ledger_inbox",
    ]
    for table in tenant_tables:
        session.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        session.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        session.execute(
            text(
                f"CREATE POLICY tenant_isolation ON {table} "
                f"USING (tenant_id = current_setting('app.tenant_id', true)::text)"
            )
        )


def _revert_rls_policies(session: Session) -> None:
    """Revert RLS policies."""
    tenant_tables = [
        "ledger_accounts",
        "ledger_journal_entries",
        "ledger_profit_thresholds",
        "ledger_profit_reservations",
        "ledger_withdrawals",
        "ledger_reconciliations",
        "ledger_positions",
        "ledger_realized_pnl",
        "ledger_outbox",
        "ledger_inbox",
    ]
    for table in tenant_tables:
        session.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        session.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))


def _apply_append_only_trigger(session: Session) -> None:
    """Add a trigger that prevents UPDATE/DELETE on journal entries.

    Per E2 scope: append-only — journal entries are INSERT-only once
    posted. The trigger raises an exception on any UPDATE or DELETE.
    """
    session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION prevent_journal_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'journal_entries is append-only: UPDATE and DELETE are not allowed';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    session.execute(
        text(
            """
            DROP TRIGGER IF EXISTS no_update_journal ON ledger_journal_entries;
            CREATE TRIGGER no_update_journal
                BEFORE UPDATE ON ledger_journal_entries
                FOR EACH STATEMENT
                EXECUTE FUNCTION prevent_journal_mutation();
            """
        )
    )
    session.execute(
        text(
            """
            DROP TRIGGER IF EXISTS no_delete_journal ON ledger_journal_entries;
            CREATE TRIGGER no_delete_journal
                BEFORE DELETE ON ledger_journal_entries
                FOR EACH STATEMENT
                EXECUTE FUNCTION prevent_journal_mutation();
            """
        )
    )


def _revert_append_only_trigger(session: Session) -> None:
    """Revert the append-only trigger."""
    session.execute(text("DROP TRIGGER IF EXISTS no_update_journal ON ledger_journal_entries"))
    session.execute(text("DROP TRIGGER IF EXISTS no_delete_journal ON ledger_journal_entries"))
    session.execute(text("DROP FUNCTION IF EXISTS prevent_journal_mutation()"))


def get_ledger_schema_version(engine: Any) -> int:
    """Return the highest applied ledger migration version, or 0."""
    with Session(engine) as session:
        try:
            result = session.execute(text("SELECT MAX(version) FROM ledger_schema_version"))
            row = result.fetchone()
            if row is not None and row[0] is not None:
                return int(row[0])
        except Exception:
            return 0
    return 0


def run_ledger_migrations_up(engine: Any) -> int:
    """Apply all pending ledger migrations. Returns the applied version."""
    LedgerBase.metadata.create_all(engine, checkfirst=True)
    with Session(engine) as session:
        current = get_ledger_schema_version(engine)
        for version, description, _up, _down in LEDGER_MIGRATIONS:
            if version <= current:
                continue
            if version == RLS_MIGRATION_VERSION and _is_postgres(engine):
                _apply_rls_policies(session)
            if version == APPEND_ONLY_MIGRATION_VERSION and _is_postgres(engine):
                _apply_append_only_trigger(session)
            session.add(
                LedgerSchemaVersionRow(
                    version=version,
                    description=description,
                    applied_at=_now_str(),
                )
            )
            session.commit()
    return LEDGER_CURRENT_VERSION


def run_ledger_migrations_down(engine: Any, target_version: int = 0) -> int:
    """Revert migrations down to *target_version*. Returns the resulting version."""
    with Session(engine) as session:
        current = get_ledger_schema_version(engine)
        for version, _desc, _up, _down in reversed(LEDGER_MIGRATIONS):
            if version <= target_version:
                break
            if version > current:
                continue
            if version == APPEND_ONLY_MIGRATION_VERSION and _is_postgres(engine):
                _revert_append_only_trigger(session)
            if version == RLS_MIGRATION_VERSION and _is_postgres(engine):
                _revert_rls_policies(session)
            session.execute(
                text("DELETE FROM ledger_schema_version WHERE version = :v"),
                {"v": version},
            )
            session.commit()
    if target_version == 0:
        LedgerBase.metadata.drop_all(engine)
    return target_version


def verify_ledger_schema(engine: Any) -> dict[str, bool]:
    """Verify the ledger schema is correctly applied. Returns a checklist."""
    checks: dict[str, bool] = {}
    with Session(engine) as session:
        # Check tables exist
        for table_name in [
            "ledger_accounts",
            "ledger_journal_entries",
            "ledger_journal_lines",
            "ledger_idempotency_keys",
            "ledger_fill_mappings",
            "ledger_profit_thresholds",
            "ledger_profit_reservations",
            "ledger_withdrawals",
            "ledger_reconciliations",
            "ledger_positions",
            "ledger_realized_pnl",
            "ledger_outbox",
            "ledger_inbox",
        ]:
            try:
                session.execute(text(f"SELECT 1 FROM {table_name} LIMIT 1"))
                checks[table_name] = True
            except Exception:
                checks[table_name] = False
    return checks
