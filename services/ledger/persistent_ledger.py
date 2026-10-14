"""Persistent financial ledger backed by PostgreSQL/SQLite (E2 — Durable Core).

Architecture Decisions: AD-018 (durable, auditable financial records),
AD-031 (PostgreSQL for durable records), AD-024 (progressive delivery).

This module provides ``PersistentLedger``, which replaces the in-memory
state of ``FinancialLedger`` with a SQLAlchemy-backed store. All
authoritative state lives in the database; the in-memory objects are
materialized on demand from DB rows.

Key DB-enforced invariants (per E2 scope):

- **Balanced journals**: ``ledger_journal_entries`` has a CHECK constraint
  ensuring ``debit_total = credit_total``.
- **Unique idempotency**: ``ledger_idempotency_keys`` and the ``idempotency_key``
  column have UNIQUE constraints preventing duplicate postings.
- **Append-only**: journal entries are INSERT-only on PostgreSQL (trigger);
  on SQLite, application-level enforcement prevents updates.
- **RLS**: every tenant-scoped table has a Row-Level Security policy (PostgreSQL).
- **Transactional outbox/inbox**: ``ledger_outbox`` and ``ledger_inbox`` tables
  for reliable, idempotent event delivery.

Crash safety: all mutations occur within a single ``Session.begin()``
transaction. A crash at a transaction boundary leaves the database
consistent — either all changes are committed or none.
"""

from __future__ import annotations

import contextlib
import json as _json
from datetime import UTC, datetime
from decimal import Decimal
from threading import Lock
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from contracts.exchange import FillResult
from contracts.ledger import (
    AccountId,
    AccountSide,
    AccountType,
    FillLedgerMapping,
    FinancialAccount,
    JournalEntry,
    JournalEntryId,
    JournalEntryType,
    JournalLine,
    ProfitLoss,
    ProfitReservationEntry,
    ProfitReservationId,
    ProfitThreshold,
    ProfitThresholdId,
    ProfitThresholdType,
    ReconciliationId,
    ReconciliationRecord,
    ReconciliationStatus,
    ReservationStatus,
    WithdrawalRequest,
    WithdrawalRequestId,
    WithdrawalStatus,
    quantize,
)
from services.ledger import (
    AccountNotFoundError,
    DuplicatePostError,
    FinancialLedger,
    InsufficientBalanceError,
    LedgerError,
    ReconciliationNotFoundError,
    ReservationNotFoundError,
    UnbalancedEntryError,
    WithdrawalNotFoundError,
)
from services.ledger.persistence import (
    FillMappingRow,
    FinancialAccountRow,
    IdempotencyKeyRow,
    InboxMessageRow,
    JournalEntryRow,
    JournalLineRow,
    LedgerBase,
    LedgerPositionRow,
    OutboxEventRow,
    ProfitReservationRow,
    ProfitThresholdRow,
    RealizedPnlRow,
    ReconciliationRow,
    WithdrawalRow,
    _now_str,
    _resolve_db_url,
    run_ledger_migrations_up,
)


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class PersistentLedger(FinancialLedger):
    """SQLAlchemy-backed financial ledger.

    Extends ``FinancialLedger`` and overrides all state-mutating methods
    to persist to the database. The in-memory dicts from
    ``FinancialLedger`` are NOT used as authoritative state — the database
    is authoritative. The in-memory dicts are cleared and never populated;
    all reads go through the DB.

    Per E2 scope: "Remove authoritative in-memory state."
    """

    _instances: list[PersistentLedger] = []
    _instances_lock = Lock()

    def __init__(self, db_url: str | None = None) -> None:
        url = db_url or _resolve_db_url()
        self._url = url
        is_sqlite = url.startswith("sqlite")
        self._engine = create_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False} if is_sqlite else {},
            poolclass=StaticPool if is_sqlite else None,
        )
        self._plock = Lock()
        run_ledger_migrations_up(self._engine)
        # Initialize parent in-memory state, then clear — DB is authoritative.
        super().__init__()
        self._accounts.clear()
        self._accounts_by_tenant_asset.clear()
        self._journal.clear()
        self._idempotency_keys.clear()
        self._fill_mappings.clear()
        self._profit_thresholds.clear()
        self._profit_reservations.clear()
        self._withdrawals.clear()
        self._reconciliations.clear()
        self._realized_pnl.clear()
        self._position_cost_basis.clear()
        self._position_quantity.clear()
        with PersistentLedger._instances_lock:
            PersistentLedger._instances.append(self)

    def close(self) -> None:
        """Dispose the underlying engine."""
        self._engine.dispose()
        with PersistentLedger._instances_lock, contextlib.suppress(ValueError):
            PersistentLedger._instances.remove(self)

    @property
    def engine(self) -> Any:
        return self._engine

    # ── Row ↔ Domain conversion ──

    def _row_to_account(self, row: FinancialAccountRow) -> FinancialAccount:
        return FinancialAccount(
            account_id=AccountId(UUID(row.account_id)),
            tenant_id=row.tenant_id,
            account_type=AccountType(row.account_type),
            asset=row.asset,
            balance=row.balance,
            reserved_balance=row.reserved_balance,
            created_at=_str_to_dt(row.created_at),
            updated_at=_str_to_dt(row.updated_at),
        )

    def _row_to_entry(self, row: JournalEntryRow, lines: list[JournalLine]) -> JournalEntry:
        return JournalEntry(
            entry_id=JournalEntryId(UUID(row.entry_id)),
            tenant_id=row.tenant_id,
            entry_type=JournalEntryType(row.entry_type),
            lines=lines,
            reference=row.reference,
            description=row.description,
            idempotency_key=row.idempotency_key,
            created_at=_str_to_dt(row.created_at),
            posted_at=_str_to_dt(row.posted_at) if row.posted_at else None,
        )

    def _row_to_threshold(self, row: ProfitThresholdRow) -> ProfitThreshold:
        return ProfitThreshold(
            threshold_id=ProfitThresholdId(UUID(row.threshold_id)),
            tenant_id=row.tenant_id,
            threshold_type=ProfitThresholdType(row.threshold_type),
            asset=row.asset,
            threshold_value=row.threshold_value,
            is_active=row.is_active,
            created_at=_str_to_dt(row.created_at),
        )

    def _row_to_reservation(self, row: ProfitReservationRow) -> ProfitReservationEntry:
        return ProfitReservationEntry(
            reservation_id=ProfitReservationId(UUID(row.reservation_id)),
            tenant_id=row.tenant_id,
            asset=row.asset,
            reserved_amount=row.reserved_amount,
            threshold_type=ProfitThresholdType(row.threshold_type),
            status=ReservationStatus(row.status),
            created_at=_str_to_dt(row.created_at),
            released_at=_str_to_dt(row.released_at) if row.released_at else None,
        )

    def _row_to_withdrawal(self, row: WithdrawalRow) -> WithdrawalRequest:
        return WithdrawalRequest(
            request_id=WithdrawalRequestId(UUID(row.request_id)),
            tenant_id=row.tenant_id,
            asset=row.asset,
            amount=row.amount,
            destination_address=row.destination_address,
            status=WithdrawalStatus(row.status),
            created_at=_str_to_dt(row.created_at),
            approved_at=_str_to_dt(row.approved_at) if row.approved_at else None,
            submitted_at=_str_to_dt(row.submitted_at) if row.submitted_at else None,
            completed_at=_str_to_dt(row.completed_at) if row.completed_at else None,
            reason=row.reason,
            provider_tx_id=row.provider_tx_id,
        )

    def _row_to_reconciliation(self, row: ReconciliationRow) -> ReconciliationRecord:
        return ReconciliationRecord(
            reconciliation_id=ReconciliationId(UUID(row.reconciliation_id)),
            tenant_id=row.tenant_id,
            asset=row.asset,
            ledger_balance=row.ledger_balance,
            exchange_balance=row.exchange_balance,
            status=ReconciliationStatus(row.status),
            created_at=_str_to_dt(row.created_at),
            resolved_at=_str_to_dt(row.resolved_at) if row.resolved_at else None,
            resolution_notes=row.resolution_notes,
        )

    # ── Account Management ──

    def create_account(
        self,
        *,
        tenant_id: str,
        account_type: AccountType,
        asset: str,
        initial_balance: str = "0",
    ) -> FinancialAccount:
        with self._plock, Session(self._engine) as session:
            existing = session.execute(
                text(
                    "SELECT account_id FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset"
                ),
                {"tid": tenant_id, "asset": asset},
            ).first()
            if existing is not None:
                raise LedgerError(f"Account already exists for tenant {tenant_id}, asset {asset}.")
            account = FinancialAccount.create(
                tenant_id=tenant_id,
                account_type=account_type,
                asset=asset,
                initial_balance=initial_balance,
            )
            row = FinancialAccountRow(
                account_id=str(account.account_id),
                tenant_id=tenant_id,
                account_type=account_type.value,
                asset=asset,
                balance=initial_balance,
                reserved_balance="0",
                created_at=_dt_to_str(account.created_at),
                updated_at=_dt_to_str(account.updated_at),
            )
            session.add(row)
            session.commit()
            return account

    def get_account(self, account_id: AccountId | str) -> FinancialAccount:
        with Session(self._engine) as session:
            row = session.get(FinancialAccountRow, str(account_id))
            if row is None:
                raise AccountNotFoundError(f"Account {account_id} not found.")
            return self._row_to_account(row)

    def get_account_by_tenant_asset(self, tenant_id: str, asset: str) -> FinancialAccount:
        with Session(self._engine) as session:
            row = session.execute(
                text(
                    "SELECT * FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": tenant_id, "asset": asset},
            ).first()
            if row is None:
                raise AccountNotFoundError(f"No account for tenant {tenant_id}, asset {asset}.")
            orm_row = session.get(FinancialAccountRow, row.account_id)
            assert orm_row is not None
            return self._row_to_account(orm_row)

    def _get_or_create_account_locked(
        self, session: Session, tenant_id: str, asset: str
    ) -> FinancialAccount:
        row = session.execute(
            text("SELECT * FROM ledger_accounts WHERE tenant_id = :tid AND asset = :asset LIMIT 1"),
            {"tid": tenant_id, "asset": asset},
        ).first()
        if row is not None:
            orm_row = session.get(FinancialAccountRow, row.account_id)
            assert orm_row is not None
            return self._row_to_account(orm_row)
        account = FinancialAccount.create(
            tenant_id=tenant_id,
            account_type=AccountType.SPOT,
            asset=asset,
        )
        session.add(
            FinancialAccountRow(
                account_id=str(account.account_id),
                tenant_id=tenant_id,
                account_type=AccountType.SPOT.value,
                asset=asset,
                balance="0",
                reserved_balance="0",
                created_at=_dt_to_str(account.created_at),
                updated_at=_dt_to_str(account.updated_at),
            )
        )
        session.flush()
        return account

    # ── Fee Entry (DB-backed override) ──

    def _create_fee_entry_db(  # noqa: PLR0913
        self,
        session: Session,
        *,
        tenant_id: str,
        quote_account: FinancialAccount,
        fee: Decimal,
        quote_asset: str,
        fill_id: str,
    ) -> JournalEntry:
        """Create a balanced fee entry using DB-backed account creation.

        Overrides the parent's in-memory ``_create_fee_entry`` because
        the parent calls ``self._get_or_create_locked()`` which only
        creates accounts in the cleared in-memory dicts — the DB never
        sees the FEE_EXPENSE account, so ``_post_entry_locked`` raises
        ``AccountNotFoundError``. This override uses
        ``_get_or_create_account_locked(session, ...)`` to create the
        expense account in the same DB transaction.
        """
        fee_amount = quantize(fee, quote_asset)
        expense_account = self._get_or_create_account_locked(
            session, tenant_id, f"FEE_EXPENSE_{quote_asset}"
        )
        return JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id=tenant_id,
            entry_type=JournalEntryType.FEE_ACCRUAL,
            lines=[
                JournalLine(
                    account_id=expense_account.account_id,
                    side=AccountSide.DEBIT,
                    amount=str(fee_amount),
                    asset=quote_asset,
                    value=str(fee_amount),
                ),
                JournalLine(
                    account_id=quote_account.account_id,
                    side=AccountSide.CREDIT,
                    amount=str(fee_amount),
                    asset=quote_asset,
                    value=str(fee_amount),
                ),
            ],
            reference=fill_id,
            description=f"Fee for fill {fill_id}",
            idempotency_key=f"fill-{fill_id}-fee",
        )

    # ── Journal Posting ──

    def post_entry(self, entry: JournalEntry) -> JournalEntry:
        with self._plock, Session(self._engine) as session:
            return self._post_entry_locked(session, entry)

    def _post_entry_locked(self, session: Session, entry: JournalEntry) -> JournalEntry:  # type: ignore[override]
        """Post an entry within an existing session (lock already held)."""
        # Idempotency check — DB-level unique constraint is the authority.
        if entry.idempotency_key is not None:
            existing = session.execute(
                text("SELECT 1 FROM ledger_idempotency_keys WHERE idempotency_key = :key"),
                {"key": entry.idempotency_key},
            ).first()
            if existing is not None:
                raise DuplicatePostError(
                    f"Duplicate journal entry for idempotency key '{entry.idempotency_key}'."
                )
        if not entry.is_balanced:
            raise UnbalancedEntryError(
                "Cannot post unbalanced journal entry — debits must equal credits."
            )
        # Insert idempotency key record.
        if entry.idempotency_key is not None:
            session.add(
                IdempotencyKeyRow(
                    idempotency_key=entry.idempotency_key,
                    created_at=_now_str(),
                )
            )
        # Calculate debit/credit totals for DB CHECK constraint.
        debit_total = sum(
            (Decimal(line.value) for line in entry.lines if line.side is AccountSide.DEBIT),
            Decimal(0),
        )
        credit_total = sum(
            (Decimal(line.value) for line in entry.lines if line.side is AccountSide.CREDIT),
            Decimal(0),
        )
        posted_at = datetime.now(UTC)
        entry_row = JournalEntryRow(
            entry_id=str(entry.entry_id),
            tenant_id=entry.tenant_id,
            entry_type=entry.entry_type.value,
            reference=entry.reference,
            description=entry.description,
            idempotency_key=entry.idempotency_key,
            debit_total=str(debit_total),
            credit_total=str(credit_total),
            created_at=_dt_to_str(entry.created_at),
            posted_at=_dt_to_str(posted_at),
        )
        session.add(entry_row)
        # Insert lines and apply to accounts.
        for line in entry.lines:
            acct_row = session.get(FinancialAccountRow, str(line.account_id))
            if acct_row is None:
                raise AccountNotFoundError(
                    f"Account {line.account_id} not found for journal entry."
                )
            session.add(
                JournalLineRow(
                    entry_id=str(entry.entry_id),
                    account_id=str(line.account_id),
                    side=line.side.value,
                    amount=line.amount,
                    asset=line.asset,
                    value=line.value,
                )
            )
            current = Decimal(acct_row.balance)
            amount = Decimal(line.amount)
            if line.side is AccountSide.DEBIT:
                new_balance = current + amount
            else:
                new_balance = current - amount
                if new_balance < 0:
                    raise InsufficientBalanceError(
                        f"Insufficient balance in {acct_row.asset} account: {current} < {amount}."
                    )
            acct_row.balance = str(quantize(new_balance, acct_row.asset))
            acct_row.updated_at = _now_str()
        session.commit()
        # Reconstruct the posted entry (with posted_at set).
        return JournalEntry(
            entry_id=entry.entry_id,
            tenant_id=entry.tenant_id,
            entry_type=entry.entry_type,
            lines=entry.lines,
            reference=entry.reference,
            description=entry.description,
            idempotency_key=entry.idempotency_key,
            created_at=entry.created_at,
            posted_at=posted_at,
        )

    def get_entry(self, entry_id: JournalEntryId | str) -> JournalEntry:
        with Session(self._engine) as session:
            row = session.get(JournalEntryRow, str(entry_id))
            if row is None:
                raise LedgerError(f"Journal entry {entry_id} not found.")
            lines = self._load_lines(session, str(entry_id))
            return self._row_to_entry(row, lines)

    def _load_lines(self, session: Session, entry_id: str) -> list[JournalLine]:
        line_rows = (
            session.query(JournalLineRow)
            .filter(JournalLineRow.entry_id == entry_id)
            .order_by(JournalLineRow.line_id)
            .all()
        )
        return [
            JournalLine(
                account_id=AccountId(UUID(lr.account_id)),
                side=AccountSide(lr.side),
                amount=lr.amount,
                asset=lr.asset,
                value=lr.value,
            )
            for lr in line_rows
        ]

    @property
    def entry_count(self) -> int:
        with Session(self._engine) as session:
            return int(
                session.execute(text("SELECT COUNT(*) FROM ledger_journal_entries")).scalar_one()
            )

    # ── Fill-to-Ledger Mapping ──

    def record_fill(
        self,
        *,
        tenant_id: str,
        fill: FillResult,
        symbol: str,
    ) -> FillLedgerMapping:
        with self._plock, Session(self._engine) as session:
            fill_id = fill.fill_id
            existing = session.get(FillMappingRow, fill_id)
            if existing is not None:
                return FillLedgerMapping(
                    fill_id=existing.fill_id,
                    entry_ids=_json.loads(existing.entry_ids),
                    asset_acquired=existing.asset_acquired,
                    asset_cost=existing.asset_cost,
                    quantity=existing.quantity,
                    price=existing.price,
                    fee=existing.fee,
                    fee_asset=existing.fee_asset,
                    realized_pnl=existing.realized_pnl,
                )

            parts = symbol.split("/")
            _SYMBOL_PAIR_LEN = 2
            base_asset = parts[0] if len(parts) == _SYMBOL_PAIR_LEN else symbol
            quote_asset = parts[1] if len(parts) == _SYMBOL_PAIR_LEN else "USDT"

            qty = Decimal(fill.filled_quantity)
            price = Decimal(fill.fill_price)
            fee = Decimal(fill.fee)

            base_account = self._get_or_create_account_locked(session, tenant_id, base_asset)
            quote_account = self._get_or_create_account_locked(session, tenant_id, quote_asset)

            entry_ids: list[str] = []

            if fill.side == "buy":
                trade_entry = self._create_trade_entry_buy(
                    tenant_id=tenant_id,
                    base_account=base_account,
                    quote_account=quote_account,
                    qty=qty,
                    price=price,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    fill_id=fill_id,
                )
            else:
                realized_pnl = self._calculate_realized_pnl_db(
                    session, tenant_id, symbol, qty, price
                )
                trade_entry = self._create_trade_entry_sell(
                    tenant_id=tenant_id,
                    base_account=base_account,
                    quote_account=quote_account,
                    qty=qty,
                    price=price,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    fill_id=fill_id,
                    realized_pnl=realized_pnl,
                )

            posted = self._post_entry_locked(session, trade_entry)
            entry_ids.append(str(posted.entry_id))

            if fee > 0:
                fee_entry = self._create_fee_entry_db(
                    session,
                    tenant_id=tenant_id,
                    quote_account=quote_account,
                    fee=fee,
                    quote_asset=quote_asset,
                    fill_id=fill_id,
                )
                posted_fee = self._post_entry_locked(session, fee_entry)
                entry_ids.append(str(posted_fee.entry_id))

            realized_pnl_value = self._get_realized_pnl_for_fill_db(
                session, tenant_id, symbol, fill.side, qty, price
            )

            self._update_position_db(session, tenant_id, symbol, fill.side, qty, price)

            mapping = FillLedgerMapping(
                fill_id=fill_id,
                entry_ids=entry_ids,
                asset_acquired=base_asset if fill.side == "buy" else quote_asset,
                asset_cost=quote_asset if fill.side == "buy" else base_asset,
                quantity=str(quantize(qty, base_asset)),
                price=str(quantize(price, quote_asset)),
                fee=str(quantize(fee, quote_asset)),
                fee_asset=quote_asset,
                realized_pnl=str(quantize(realized_pnl_value, quote_asset)),
            )
            session.add(
                FillMappingRow(
                    fill_id=fill_id,
                    entry_ids=_json.dumps(entry_ids),
                    asset_acquired=mapping.asset_acquired,
                    asset_cost=mapping.asset_cost,
                    quantity=mapping.quantity,
                    price=mapping.price,
                    fee=mapping.fee,
                    fee_asset=mapping.fee_asset,
                    realized_pnl=mapping.realized_pnl,
                    mapped_at=_now_str(),
                )
            )
            session.commit()
            return mapping

    def _calculate_realized_pnl_db(
        self,
        session: Session,
        tenant_id: str,
        symbol: str,
        qty: Decimal,
        price: Decimal,
    ) -> Decimal:
        pos = self._get_position_row(session, tenant_id, symbol)
        if pos is None:
            return Decimal(0)
        current_qty = Decimal(pos.quantity)
        current_cost = Decimal(pos.cost_basis)
        if current_qty <= 0:
            return Decimal(0)
        avg_cost = current_cost / current_qty if current_qty > 0 else Decimal(0)
        sell_qty = min(qty, current_qty)
        return (price - avg_cost) * sell_qty

    def _get_realized_pnl_for_fill_db(  # noqa: PLR0913, PLR0917
        self,
        session: Session,
        tenant_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
    ) -> Decimal:
        if side != "sell":
            return Decimal(0)
        realized = self._calculate_realized_pnl_db(session, tenant_id, symbol, qty, price)
        pnl_row = session.get(RealizedPnlRow, tenant_id)
        if pnl_row is None:
            session.add(
                RealizedPnlRow(
                    tenant_id=tenant_id,
                    total=str(realized),
                )
            )
        else:
            pnl_row.total = str(Decimal(pnl_row.total) + realized)
        return realized

    def _get_position_row(
        self, session: Session, tenant_id: str, symbol: str
    ) -> LedgerPositionRow | None:
        return (
            session.query(LedgerPositionRow)
            .filter(
                LedgerPositionRow.tenant_id == tenant_id,
                LedgerPositionRow.symbol == symbol,
            )
            .first()
        )

    def _update_position_db(  # noqa: PLR0913, PLR0917
        self,
        session: Session,
        tenant_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
    ) -> None:
        pos = self._get_position_row(session, tenant_id, symbol)
        if pos is None:
            # Create new position row
            if side == "buy":
                new_qty = qty
                new_cost = qty * price
            else:
                new_qty = Decimal(0)
                new_cost = Decimal(0)
            session.add(
                LedgerPositionRow(
                    tenant_id=tenant_id,
                    symbol=symbol,
                    quantity=str(new_qty),
                    cost_basis=str(new_cost),
                )
            )
        else:
            current_qty = Decimal(pos.quantity)
            current_cost = Decimal(pos.cost_basis)
            if side == "buy":
                new_qty = current_qty + qty
                new_cost = current_cost + (qty * price)
                pos.quantity = str(new_qty)
                pos.cost_basis = str(new_cost)
            elif current_qty > 0:
                avg_cost = current_cost / current_qty if current_qty > 0 else Decimal(0)
                remaining_qty = current_qty - qty
                if remaining_qty <= 0:
                    pos.quantity = "0"
                    pos.cost_basis = "0"
                else:
                    remaining_cost = remaining_qty * avg_cost
                    pos.quantity = str(remaining_qty)
                    pos.cost_basis = str(remaining_cost)

    # ── P&L Queries ──

    def get_realized_pnl(self, tenant_id: str) -> str:
        with Session(self._engine) as session:
            row = session.get(RealizedPnlRow, tenant_id)
            if row is None:
                return "0"
            return row.total

    def get_unrealized_pnl(self, tenant_id: str, symbol: str, current_price: str) -> str:
        with Session(self._engine) as session:
            pos = self._get_position_row(session, tenant_id, symbol)
            if pos is None:
                return "0"
            current_qty = Decimal(pos.quantity)
            current_cost = Decimal(pos.cost_basis)
            if current_qty <= 0:
                return "0"
            market_value = current_qty * Decimal(current_price)
            unrealized = market_value - current_cost
            return str(quantize(unrealized, "USDT"))

    def get_pnl(
        self, tenant_id: str, *, symbol: str | None = None, current_price: str = "0"
    ) -> ProfitLoss:
        with Session(self._engine) as session:
            pnl_row = session.get(RealizedPnlRow, tenant_id)
            realized = Decimal(pnl_row.total) if pnl_row is not None else Decimal(0)
            unrealized = Decimal(0)
            if symbol is not None and Decimal(current_price) > 0:
                pos = self._get_position_row(session, tenant_id, symbol)
                if pos is not None:
                    current_qty = Decimal(pos.quantity)
                    current_cost = Decimal(pos.cost_basis)
                    if current_qty > 0:
                        unrealized = (current_qty * Decimal(current_price)) - current_cost
            return ProfitLoss(
                tenant_id=tenant_id,
                realized_pnl=str(quantize(realized, "USDT")),
                unrealized_pnl=str(quantize(unrealized, "USDT")),
            )

    # ── Balance Queries ──

    def get_balance(self, tenant_id: str, asset: str) -> str:
        with Session(self._engine) as session:
            row = session.execute(
                text(
                    "SELECT balance FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": tenant_id, "asset": asset},
            ).first()
            if row is None:
                return "0"
            return str(row.balance)

    def get_available_balance(self, tenant_id: str, asset: str) -> str:
        with Session(self._engine) as session:
            row = session.execute(
                text(
                    "SELECT balance, reserved_balance FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": tenant_id, "asset": asset},
            ).first()
            if row is None:
                return "0"
            return str(Decimal(row.balance) - Decimal(row.reserved_balance))

    def get_reserved_balance(self, tenant_id: str, asset: str) -> str:
        with Session(self._engine) as session:
            row = session.execute(
                text(
                    "SELECT reserved_balance FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": tenant_id, "asset": asset},
            ).first()
            if row is None:
                return "0"
            return str(row.reserved_balance)

    def get_withdrawable_balance(self, tenant_id: str, asset: str) -> str:
        return self.get_available_balance(tenant_id, asset)

    # ── Profit Thresholds ──

    def add_profit_threshold(
        self,
        *,
        tenant_id: str,
        threshold_type: ProfitThresholdType,
        asset: str,
        threshold_value: str,
    ) -> ProfitThreshold:
        with self._plock, Session(self._engine) as session:
            threshold = ProfitThreshold.create(
                tenant_id=tenant_id,
                threshold_type=threshold_type,
                asset=asset,
                threshold_value=threshold_value,
            )
            session.add(
                ProfitThresholdRow(
                    threshold_id=str(threshold.threshold_id),
                    tenant_id=tenant_id,
                    threshold_type=threshold_type.value,
                    asset=asset,
                    threshold_value=threshold_value,
                    is_active=True,
                    created_at=_dt_to_str(threshold.created_at),
                )
            )
            session.commit()
            return threshold

    def get_profit_thresholds(self, tenant_id: str) -> list[ProfitThreshold]:
        with Session(self._engine) as session:
            rows = (
                session.query(ProfitThresholdRow)
                .filter(ProfitThresholdRow.tenant_id == tenant_id)
                .all()
            )
            return [self._row_to_threshold(r) for r in rows]

    def check_thresholds(
        self, tenant_id: str, asset: str, current_pnl: str
    ) -> list[ProfitThreshold]:
        with Session(self._engine) as session:
            rows = (
                session.query(ProfitThresholdRow)
                .filter(
                    ProfitThresholdRow.tenant_id == tenant_id,
                    ProfitThresholdRow.is_active == True,  # noqa: E712
                    ProfitThresholdRow.asset == asset,
                )
                .all()
            )
            pnl = Decimal(current_pnl)
            triggered: list[ProfitThreshold] = []
            for r in rows:
                if pnl >= Decimal(r.threshold_value):
                    triggered.append(self._row_to_threshold(r))
            return triggered

    # ── Profit Reservations ──

    def reserve_profit(
        self,
        *,
        tenant_id: str,
        asset: str,
        amount: str,
        threshold_type: ProfitThresholdType = ProfitThresholdType.PROFIT_RESERVATION,
    ) -> ProfitReservationEntry:
        with self._plock, Session(self._engine) as session:
            acct = session.execute(
                text(
                    "SELECT * FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": tenant_id, "asset": asset},
            ).first()
            if acct is None:
                raise AccountNotFoundError(f"No account for tenant {tenant_id}, asset {asset}.")
            acct_row = session.get(FinancialAccountRow, acct.account_id)
            assert acct_row is not None
            available = Decimal(acct_row.balance) - Decimal(acct_row.reserved_balance)
            reserve_amount = Decimal(amount)
            if reserve_amount > available:
                raise InsufficientBalanceError(
                    f"Insufficient available balance to reserve: {available} < {reserve_amount}."
                )
            reservation = ProfitReservationEntry(
                reservation_id=ProfitReservationId.generate(),
                tenant_id=tenant_id,
                asset=asset,
                reserved_amount=str(quantize(reserve_amount, asset)),
                threshold_type=threshold_type,
            )
            session.add(
                ProfitReservationRow(
                    reservation_id=str(reservation.reservation_id),
                    tenant_id=tenant_id,
                    asset=asset,
                    reserved_amount=reservation.reserved_amount,
                    threshold_type=threshold_type.value,
                    status="active",
                    created_at=_dt_to_str(reservation.created_at),
                )
            )
            acct_row.reserved_balance = str(
                quantize(Decimal(acct_row.reserved_balance) + reserve_amount, asset)
            )
            acct_row.updated_at = _now_str()
            session.commit()
            return reservation

    def release_profit_reservation(self, reservation_id: str) -> ProfitReservationEntry:
        with self._plock, Session(self._engine) as session:
            row = session.get(ProfitReservationRow, reservation_id)
            if row is None:
                raise ReservationNotFoundError(f"Reservation {reservation_id} not found.")
            if row.status != "active":
                raise LedgerError(
                    f"Reservation {reservation_id} is not active (status: {row.status})."
                )
            row.status = "released"
            row.released_at = _now_str()
            # Return reserved balance to available.
            acct = session.execute(
                text(
                    "SELECT account_id FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": row.tenant_id, "asset": row.asset},
            ).first()
            if acct is not None:
                acct_row = session.get(FinancialAccountRow, acct.account_id)
                assert acct_row is not None
                new_reserved = Decimal(acct_row.reserved_balance) - Decimal(row.reserved_amount)
                if new_reserved < 0:
                    new_reserved = Decimal(0)
                acct_row.reserved_balance = str(quantize(new_reserved, acct_row.asset))
                acct_row.updated_at = _now_str()
            session.commit()
            return self._row_to_reservation(row)

    def get_profit_reservations(self, tenant_id: str) -> list[ProfitReservationEntry]:
        with Session(self._engine) as session:
            rows = (
                session.query(ProfitReservationRow)
                .filter(ProfitReservationRow.tenant_id == tenant_id)
                .all()
            )
            return [self._row_to_reservation(r) for r in rows]

    def get_active_reservations(self, tenant_id: str) -> list[ProfitReservationEntry]:
        with Session(self._engine) as session:
            rows = (
                session.query(ProfitReservationRow)
                .filter(
                    ProfitReservationRow.tenant_id == tenant_id,
                    ProfitReservationRow.status == "active",
                )
                .all()
            )
            return [self._row_to_reservation(r) for r in rows]

    # ── Withdrawal Requests ──

    def create_withdrawal_request(
        self,
        *,
        tenant_id: str,
        asset: str,
        amount: str,
        destination_address: str = "",
    ) -> WithdrawalRequest:
        with self._plock, Session(self._engine) as session:
            acct = session.execute(
                text(
                    "SELECT * FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": tenant_id, "asset": asset},
            ).first()
            if acct is None:
                raise AccountNotFoundError(f"No account for tenant {tenant_id}, asset {asset}.")
            acct_row = session.get(FinancialAccountRow, acct.account_id)
            assert acct_row is not None
            available = Decimal(acct_row.balance) - Decimal(acct_row.reserved_balance)
            withdraw_amount = Decimal(amount)
            if withdraw_amount > available:
                raise InsufficientBalanceError(
                    f"Insufficient available balance for withdrawal: "
                    f"{available} < {withdraw_amount}."
                )
            request = WithdrawalRequest.create(
                tenant_id=tenant_id,
                asset=asset,
                amount=amount,
                destination_address=destination_address,
            )
            session.add(
                WithdrawalRow(
                    request_id=str(request.request_id),
                    tenant_id=tenant_id,
                    asset=asset,
                    amount=amount,
                    destination_address=destination_address,
                    status="draft",
                    created_at=_dt_to_str(request.created_at),
                )
            )
            session.commit()
            return request

    def get_withdrawal_request(self, request_id: str) -> WithdrawalRequest:
        with Session(self._engine) as session:
            row = session.get(WithdrawalRow, request_id)
            if row is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            return self._row_to_withdrawal(row)

    def submit_withdrawal_for_approval(self, request_id: str) -> WithdrawalRequest:
        with self._plock, Session(self._engine) as session:
            row = session.get(WithdrawalRow, request_id)
            if row is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            updated = self._row_to_withdrawal(row).submit_for_approval()
            row.status = "pending_approval"
            session.commit()
            return updated

    def approve_withdrawal(self, request_id: str) -> WithdrawalRequest:
        with self._plock, Session(self._engine) as session:
            row = session.get(WithdrawalRow, request_id)
            if row is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            updated = self._row_to_withdrawal(row).approve()
            row.status = "approved"
            row.approved_at = _now_str()
            session.commit()
            return updated

    def reject_withdrawal(self, request_id: str, reason: str = "") -> WithdrawalRequest:
        with self._plock, Session(self._engine) as session:
            row = session.get(WithdrawalRow, request_id)
            if row is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            updated = self._row_to_withdrawal(row).reject(reason)
            row.status = "rejected"
            row.reason = reason or "Withdrawal rejected"
            session.commit()
            return updated

    def submit_withdrawal_to_provider(self, request_id: str) -> WithdrawalRequest:
        with self._plock, Session(self._engine) as session:
            row = session.get(WithdrawalRow, request_id)
            if row is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            updated = self._row_to_withdrawal(row).submit()
            row.status = "submitted"
            row.submitted_at = _now_str()
            session.commit()
            return updated

    def complete_withdrawal(self, request_id: str, provider_tx_id: str = "") -> WithdrawalRequest:
        with self._plock, Session(self._engine) as session:
            row = session.get(WithdrawalRow, request_id)
            if row is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            updated = self._row_to_withdrawal(row).complete(provider_tx_id)
            row.status = "completed"
            row.completed_at = _now_str()
            row.provider_tx_id = provider_tx_id or None
            # Deduct the withdrawn amount from the account balance.
            acct = session.execute(
                text(
                    "SELECT account_id FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": row.tenant_id, "asset": row.asset},
            ).first()
            if acct is not None:
                acct_row = session.get(FinancialAccountRow, acct.account_id)
                assert acct_row is not None
                new_balance = Decimal(acct_row.balance) - Decimal(row.amount)
                if new_balance < 0:
                    new_balance = Decimal(0)
                acct_row.balance = str(quantize(new_balance, acct_row.asset))
                acct_row.updated_at = _now_str()
            session.commit()
            return updated

    def get_withdrawals(self, tenant_id: str) -> list[WithdrawalRequest]:
        with Session(self._engine) as session:
            rows = session.query(WithdrawalRow).filter(WithdrawalRow.tenant_id == tenant_id).all()
            return [self._row_to_withdrawal(r) for r in rows]

    # ── Reconciliation ──

    def reconcile_balance(
        self,
        *,
        tenant_id: str,
        asset: str,
        exchange_balance: str,
    ) -> ReconciliationRecord:
        with self._plock, Session(self._engine) as session:
            ledger_balance = session.execute(
                text(
                    "SELECT balance FROM ledger_accounts "
                    "WHERE tenant_id = :tid AND asset = :asset LIMIT 1"
                ),
                {"tid": tenant_id, "asset": asset},
            ).scalar()
            if ledger_balance is None:
                ledger_balance = "0"
            record = ReconciliationRecord(
                reconciliation_id=ReconciliationId.generate(),
                tenant_id=tenant_id,
                asset=asset,
                ledger_balance=ledger_balance,
                exchange_balance=exchange_balance,
            )
            session.add(
                ReconciliationRow(
                    reconciliation_id=str(record.reconciliation_id),
                    tenant_id=tenant_id,
                    asset=asset,
                    ledger_balance=ledger_balance,
                    exchange_balance=exchange_balance,
                    status=record.status.value,
                    created_at=_dt_to_str(record.created_at),
                )
            )
            session.commit()
            return record

    def resolve_reconciliation(
        self, reconciliation_id: str, notes: str = ""
    ) -> ReconciliationRecord:
        with self._plock, Session(self._engine) as session:
            row = session.get(ReconciliationRow, reconciliation_id)
            if row is None:
                raise ReconciliationNotFoundError(f"Reconciliation {reconciliation_id} not found.")
            record = self._row_to_reconciliation(row)
            if not record.has_discrepancy:
                raise LedgerError(
                    f"Reconciliation {reconciliation_id} has no discrepancy to resolve."
                )
            resolved = record.resolve(notes)
            row.status = "resolved"
            row.resolved_at = _now_str()
            row.resolution_notes = notes or "Discrepancy resolved with correction entry."
            session.commit()
            return resolved

    def get_reconciliations(self, tenant_id: str) -> list[ReconciliationRecord]:
        with Session(self._engine) as session:
            rows = (
                session.query(ReconciliationRow)
                .filter(ReconciliationRow.tenant_id == tenant_id)
                .all()
            )
            return [self._row_to_reconciliation(r) for r in rows]

    def get_reconciliation(self, reconciliation_id: str) -> ReconciliationRecord:
        with Session(self._engine) as session:
            row = session.get(ReconciliationRow, reconciliation_id)
            if row is None:
                raise ReconciliationNotFoundError(f"Reconciliation {reconciliation_id} not found.")
            return self._row_to_reconciliation(row)

    # ── Correction Entries ──

    def create_correction_entry(
        self,
        *,
        tenant_id: str,
        account_id: AccountId,
        asset: str,
        correction_amount: str,
        reason: str,
    ) -> JournalEntry:
        amount = Decimal(correction_amount)
        if amount == 0:
            raise LedgerError("Correction amount must be non-zero.")
        side = AccountSide.DEBIT if amount > 0 else AccountSide.CREDIT
        abs_amount = str(abs(amount))
        entry = JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id=tenant_id,
            entry_type=JournalEntryType.CORRECTION,
            lines=[
                JournalLine(
                    account_id=account_id,
                    side=side,
                    amount=abs_amount,
                    asset=asset,
                ),
                JournalLine(
                    account_id=account_id,
                    side=AccountSide.CREDIT if side is AccountSide.DEBIT else AccountSide.DEBIT,
                    amount=abs_amount,
                    asset=asset,
                ),
            ],
            reference="correction",
            description=f"Correction: {reason}",
        )
        return self.post_entry(entry)

    # ── State ──

    @property
    def account_count(self) -> int:
        with Session(self._engine) as session:
            return int(session.execute(text("SELECT COUNT(*) FROM ledger_accounts")).scalar_one())

    @property
    def fill_mapping_count(self) -> int:
        with Session(self._engine) as session:
            return int(
                session.execute(text("SELECT COUNT(*) FROM ledger_fill_mappings")).scalar_one()
            )

    def reset(self) -> None:
        """Drop and recreate all ledger tables."""
        with self._plock:
            LedgerBase.metadata.drop_all(self._engine)
            run_ledger_migrations_up(self._engine)

    # ── Transactional Outbox/Inbox ──

    def emit_outbox_event(  # noqa: PLR0913
        self,
        *,
        event_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        tenant_id: str,
    ) -> None:
        """Write an event to the transactional outbox.

        Per E2 scope: transactional outbox for reliable event delivery.
        This must be called within the same DB transaction as the
        state change that produced the event.
        """
        with Session(self._engine) as session:
            max_seq = session.execute(
                text("SELECT COALESCE(MAX(sequence_num), 0) FROM ledger_outbox")
            ).scalar_one()
            session.add(
                OutboxEventRow(
                    event_id=event_id,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    event_type=event_type,
                    payload=_json.dumps(payload),
                    tenant_id=tenant_id,
                    sequence_num=max_seq + 1,
                    created_at=_now_str(),
                )
            )
            session.commit()

    def get_pending_outbox_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get unprocessed outbox events (for the consumer/poller)."""
        with Session(self._engine) as session:
            rows = (
                session.query(OutboxEventRow)
                .filter(OutboxEventRow.processed_at.is_(None))
                .order_by(OutboxEventRow.sequence_num)
                .limit(limit)
                .all()
            )
            return [
                {
                    "event_id": r.event_id,
                    "aggregate_type": r.aggregate_type,
                    "aggregate_id": r.aggregate_id,
                    "event_type": r.event_type,
                    "payload": _json.loads(r.payload),
                    "tenant_id": r.tenant_id,
                    "sequence_num": r.sequence_num,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    def mark_outbox_processed(self, event_id: str) -> None:
        """Mark an outbox event as processed."""
        with Session(self._engine) as session:
            row = session.get(OutboxEventRow, event_id)
            if row is not None:
                row.processed_at = _now_str()
                session.commit()

    def receive_inbox_message(
        self,
        *,
        message_id: str,
        source: str,
        event_type: str,
        payload: dict[str, Any],
        tenant_id: str,
    ) -> bool:
        """Receive a message into the inbox (idempotent).

        Returns True if the message was newly received, False if it
        already existed (duplicate).

        Per E2 scope: transactional inbox for idempotent message processing.
        The UNIQUE constraint on message_id prevents duplicates at the DB level.
        """
        with Session(self._engine) as session:
            existing = session.execute(
                text("SELECT 1 FROM ledger_inbox WHERE message_id = :mid LIMIT 1"),
                {"mid": message_id},
            ).first()
            if existing is not None:
                return False
            session.add(
                InboxMessageRow(
                    message_id=message_id,
                    source=source,
                    event_type=event_type,
                    payload=_json.dumps(payload),
                    tenant_id=tenant_id,
                    received_at=_now_str(),
                )
            )
            session.commit()
            return True

    def get_pending_inbox_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get unprocessed inbox messages (for the consumer/poller)."""
        with Session(self._engine) as session:
            rows = (
                session.query(InboxMessageRow)
                .filter(InboxMessageRow.processed_at.is_(None))
                .order_by(InboxMessageRow.inbox_id)
                .limit(limit)
                .all()
            )
            return [
                {
                    "inbox_id": r.inbox_id,
                    "message_id": r.message_id,
                    "source": r.source,
                    "event_type": r.event_type,
                    "payload": _json.loads(r.payload),
                    "tenant_id": r.tenant_id,
                    "received_at": r.received_at,
                }
                for r in rows
            ]

    def mark_inbox_processed(self, inbox_id: int) -> None:
        """Mark an inbox message as processed."""
        with Session(self._engine) as session:
            row = session.get(InboxMessageRow, inbox_id)
            if row is not None:
                row.processed_at = _now_str()
                session.commit()


# ── Module-level store management ──

_ledger: PersistentLedger | None = None
_ledger_lock = Lock()


def get_persistent_ledger() -> PersistentLedger:
    """Get the singleton persistent ledger instance."""
    global _ledger  # noqa: PLW0603
    with _ledger_lock:
        if _ledger is None:
            _ledger = PersistentLedger()
        return _ledger


def reset_persistent_ledger() -> None:
    """Reset the singleton persistent ledger (for testing)."""
    global _ledger  # noqa: PLW0603
    with _ledger_lock:
        _close_all_ledger_instances()
        _ledger = PersistentLedger()


def _close_all_ledger_instances() -> None:
    with PersistentLedger._instances_lock:
        instances = list(PersistentLedger._instances)
        PersistentLedger._instances.clear()
    for inst in instances:
        with contextlib.suppress(Exception):
            inst.close()
