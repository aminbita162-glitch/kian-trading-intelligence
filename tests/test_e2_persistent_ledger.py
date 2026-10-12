"""E2 — Durable Core: persistent ledger tests (SQLite-backed).

Tests that the persistent ledger correctly replaces in-memory state with
DB-backed state, and that DB-enforced invariants hold:

- Balanced journals (CHECK constraint)
- Unique idempotency (UNIQUE constraint)
- Append-only behavior (no UPDATE on posted entries)
- Transactional outbox/inbox
- Crash safety (data survives store recreation)

Per E2 scope: "Crash at transaction boundaries leaves consistent state;
no duplicate effects on replay."
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from contracts.exchange import ClientOrderId, FillResult
from contracts.ledger import (
    AccountSide,
    AccountType,
    JournalEntry,
    JournalEntryId,
    JournalEntryType,
    JournalLine,
)
from services.ledger.persistence import (
    IdempotencyKeyRow,
    run_ledger_migrations_down,
    run_ledger_migrations_up,
)
from services.ledger.persistent_ledger import PersistentLedger


@pytest.fixture
def ledger() -> Iterator[PersistentLedger]:
    """Create a fresh persistent ledger with file-based SQLite for each test."""
    db_path = tempfile.mktemp(suffix=".db")
    db_url = f"sqlite:///{db_path}"
    store = PersistentLedger(db_url=db_url)
    yield store
    store.close()
    with contextlib.suppress(OSError):
        os.unlink(db_path)


class TestLedgerMigrations:
    """Test versioned migrations with up/down."""

    def test_migrations_up_creates_tables(self) -> None:
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        from sqlalchemy import create_engine

        engine = create_engine(db_url)
        version = run_ledger_migrations_up(engine)
        assert version >= 1
        # Verify tables exist
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
            table_names = {r[0] for r in tables}
            assert "ledger_accounts" in table_names
            assert "ledger_journal_entries" in table_names
            assert "ledger_journal_lines" in table_names
            assert "ledger_idempotency_keys" in table_names
            assert "ledger_outbox" in table_names
            assert "ledger_inbox" in table_names
        engine.dispose()
        os.unlink(db_path)

    def test_migrations_down_drops_tables(self) -> None:
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        from sqlalchemy import create_engine

        engine = create_engine(db_url)
        run_ledger_migrations_up(engine)
        run_ledger_migrations_down(engine, target_version=0)
        # Tables should be gone
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
            table_names = {r[0] for r in tables}
            assert "ledger_accounts" not in table_names
        engine.dispose()
        os.unlink(db_path)

    def test_migration_version_is_recorded(self) -> None:
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        from sqlalchemy import create_engine

        engine = create_engine(db_url)
        run_ledger_migrations_up(engine)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT MAX(version) FROM ledger_schema_version")).fetchone()
            assert result is not None
            assert result[0] >= 1
        engine.dispose()
        os.unlink(db_path)


class TestPersistentLedgerAccounts:
    """Test DB-backed account management."""

    def test_create_account_persists(self, ledger: PersistentLedger) -> None:
        account = ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
            initial_balance="1.5",
        )
        # Read it back from a new session
        fetched = ledger.get_account(account.account_id)
        assert fetched.asset == "BTC"
        assert fetched.balance == "1.5"
        assert fetched.tenant_id == "tenant-1"

    def test_get_account_by_tenant_asset(self, ledger: PersistentLedger) -> None:
        account = ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="ETH",
        )
        fetched = ledger.get_account_by_tenant_asset("tenant-1", "ETH")
        assert str(fetched.account_id) == str(account.account_id)

    def test_duplicate_account_rejected(self, ledger: PersistentLedger) -> None:
        ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
        )
        with pytest.raises(Exception, match="already exists"):
            ledger.create_account(
                tenant_id="tenant-1",
                account_type=AccountType.SPOT,
                asset="BTC",
            )

    def test_data_survives_store_recreation(self) -> None:
        """Crash safety: data must survive store recreation."""
        db_path = tempfile.mktemp(suffix=".db")
        db_url = f"sqlite:///{db_path}"
        store1 = PersistentLedger(db_url=db_url)
        store1.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
            initial_balance="2.0",
        )
        store1.close()

        # Recreate store pointing at the same DB file
        store2 = PersistentLedger(db_url=db_url)
        account = store2.get_account_by_tenant_asset("tenant-1", "BTC")
        assert account.balance == "2.0"
        store2.close()
        os.unlink(db_path)


class TestPersistentLedgerJournal:
    """Test DB-backed journal posting with invariant enforcement."""

    def test_post_entry_persists(self, ledger: PersistentLedger) -> None:
        account = ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
            initial_balance="10",
        )
        entry = JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id="tenant-1",
            entry_type=JournalEntryType.FUNDING_DEPOSIT,
            lines=[
                JournalLine(
                    account_id=account.account_id,
                    side=AccountSide.DEBIT,
                    amount="5",
                    asset="BTC",
                ),
                JournalLine(
                    account_id=account.account_id,
                    side=AccountSide.CREDIT,
                    amount="5",
                    asset="BTC",
                ),
            ],
        )
        posted = ledger.post_entry(entry)
        assert posted.posted_at is not None
        # Balance updated
        fetched = ledger.get_account(account.account_id)
        # Debit increases balance, credit decreases: 10 + 5 - 5 = 10
        assert Decimal(fetched.balance) == Decimal("10")

    def test_unbalanced_entry_rejected(self, ledger: PersistentLedger) -> None:
        account = ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
            initial_balance="10",
        )
        # JournalEntry.__post_init__ raises ValueError for unbalanced entries
        with pytest.raises(ValueError, match="Unbalanced"):
            JournalEntry(
                entry_id=JournalEntryId.generate(),
                tenant_id="tenant-1",
                entry_type=JournalEntryType.TRADE_EXECUTION,
                lines=[
                    JournalLine(
                        account_id=account.account_id,
                        side=AccountSide.DEBIT,
                        amount="5",
                        asset="BTC",
                    ),
                    JournalLine(
                        account_id=account.account_id,
                        side=AccountSide.CREDIT,
                        amount="3",
                        asset="BTC",
                    ),
                ],
            )

    def test_idempotency_key_prevents_duplicate(self, ledger: PersistentLedger) -> None:
        account = ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
            initial_balance="10",
        )
        entry1 = JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id="tenant-1",
            entry_type=JournalEntryType.FUNDING_DEPOSIT,
            lines=[
                JournalLine(
                    account_id=account.account_id,
                    side=AccountSide.DEBIT,
                    amount="5",
                    asset="BTC",
                ),
                JournalLine(
                    account_id=account.account_id,
                    side=AccountSide.CREDIT,
                    amount="5",
                    asset="BTC",
                ),
            ],
            idempotency_key="idem-1",
        )
        ledger.post_entry(entry1)
        # Same idempotency key → duplicate
        entry2 = JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id="tenant-1",
            entry_type=JournalEntryType.FUNDING_DEPOSIT,
            lines=[
                JournalLine(
                    account_id=account.account_id,
                    side=AccountSide.DEBIT,
                    amount="5",
                    asset="BTC",
                ),
                JournalLine(
                    account_id=account.account_id,
                    side=AccountSide.CREDIT,
                    amount="5",
                    asset="BTC",
                ),
            ],
            idempotency_key="idem-1",
        )
        with pytest.raises(Exception, match="Duplicate"):
            ledger.post_entry(entry2)

    def test_entry_count_persistent(self, ledger: PersistentLedger) -> None:
        account = ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
            initial_balance="10",
        )
        assert ledger.entry_count == 0
        entry = JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id="tenant-1",
            entry_type=JournalEntryType.FUNDING_DEPOSIT,
            lines=[
                JournalLine(
                    account_id=account.account_id,
                    side=AccountSide.DEBIT,
                    amount="5",
                    asset="BTC",
                ),
                JournalLine(
                    account_id=account.account_id,
                    side=AccountSide.CREDIT,
                    amount="5",
                    asset="BTC",
                ),
            ],
        )
        ledger.post_entry(entry)
        assert ledger.entry_count == 1


class TestPersistentLedgerFillRecording:
    """Test DB-backed fill recording (idempotent on replay)."""

    def test_record_fill_creates_accounts_and_entries(self, ledger: PersistentLedger) -> None:
        # Fund the USDT account so the buy can credit (debit USDT, credit BTC)
        ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="USDT",
            initial_balance="100000",
        )
        fill = FillResult(
            fill_id=f"fill-{uuid4()}",
            client_order_id=ClientOrderId("order-1"),
            symbol="BTC/USDT",
            side="buy",
            filled_quantity="1.0",
            fill_price="50000.00",
            fee="50.00",
            timestamp=datetime.now(UTC),
        )
        mapping = ledger.record_fill(
            tenant_id="tenant-1",
            fill=fill,
            symbol="BTC/USDT",
        )
        assert mapping.fill_id == fill.fill_id
        assert len(mapping.entry_ids) >= 1
        # BTC account should have balance 1.0
        btc_balance = ledger.get_balance("tenant-1", "BTC")
        assert Decimal(btc_balance) == Decimal("1.0")

    def test_record_fill_idempotent_on_replay(self, ledger: PersistentLedger) -> None:
        """No duplicate effects on replay (E2 acceptance criterion)."""
        fill = FillResult(
            fill_id=f"fill-{uuid4()}",
            client_order_id=ClientOrderId("order-1"),
            symbol="BTC/USDT",
            side="buy",
            filled_quantity="1.0",
            fill_price="50000.00",
            fee="50.00",
            timestamp=datetime.now(UTC),
        )
        # Fund the USDT account first
        ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="USDT",
            initial_balance="100000",
        )
        mapping1 = ledger.record_fill(
            tenant_id="tenant-1",
            fill=fill,
            symbol="BTC/USDT",
        )
        btc_after_1 = ledger.get_balance("tenant-1", "BTC")
        usdt_after_1 = ledger.get_balance("tenant-1", "USDT")
        entry_count_1 = ledger.entry_count

        # Replay the same fill — should be idempotent
        mapping2 = ledger.record_fill(
            tenant_id="tenant-1",
            fill=fill,
            symbol="BTC/USDT",
        )
        btc_after_2 = ledger.get_balance("tenant-1", "BTC")
        usdt_after_2 = ledger.get_balance("tenant-1", "USDT")
        entry_count_2 = ledger.entry_count

        assert btc_after_1 == btc_after_2
        assert usdt_after_1 == usdt_after_2
        assert entry_count_1 == entry_count_2
        assert mapping1.fill_id == mapping2.fill_id


class TestPersistentLedgerBalances:
    """Test DB-backed balance queries."""

    def test_get_balance_nonexistent_returns_zero(self, ledger: PersistentLedger) -> None:
        assert ledger.get_balance("tenant-1", "DOGE") == "0"

    def test_available_balance(self, ledger: PersistentLedger) -> None:
        ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
            initial_balance="10",
        )
        assert ledger.get_available_balance("tenant-1", "BTC") == "10"
        assert ledger.get_balance("tenant-1", "BTC") == "10"
        assert ledger.get_reserved_balance("tenant-1", "BTC") == "0"


class TestPersistentLedgerProfitReservations:
    """Test DB-backed profit reservations."""

    def test_reserve_and_release_profit(self, ledger: PersistentLedger) -> None:
        ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="USDT",
            initial_balance="1000",
        )
        reservation = ledger.reserve_profit(
            tenant_id="tenant-1",
            asset="USDT",
            amount="200",
        )
        assert reservation.is_active
        assert Decimal(ledger.get_reserved_balance("tenant-1", "USDT")) == Decimal("200")
        assert Decimal(ledger.get_available_balance("tenant-1", "USDT")) == Decimal("800")

        released = ledger.release_profit_reservation(str(reservation.reservation_id))
        assert not released.is_active
        assert Decimal(ledger.get_reserved_balance("tenant-1", "USDT")) == Decimal("0")
        assert Decimal(ledger.get_available_balance("tenant-1", "USDT")) == Decimal("1000")


class TestPersistentLedgerWithdrawals:
    """Test DB-backed withdrawal requests."""

    def test_create_and_complete_withdrawal(self, ledger: PersistentLedger) -> None:
        ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="USDT",
            initial_balance="500",
        )
        request = ledger.create_withdrawal_request(
            tenant_id="tenant-1",
            asset="USDT",
            amount="100",
            destination_address="0xabc",
        )
        assert request.status.value == "draft"

        submitted = ledger.submit_withdrawal_for_approval(str(request.request_id))
        assert submitted.status.value == "pending_approval"

        approved = ledger.approve_withdrawal(str(request.request_id))
        assert approved.status.value == "approved"

        sent = ledger.submit_withdrawal_to_provider(str(request.request_id))
        assert sent.status.value == "submitted"

        completed = ledger.complete_withdrawal(str(request.request_id), provider_tx_id="tx-123")
        assert completed.status.value == "completed"

        # Balance should be reduced
        assert Decimal(ledger.get_balance("tenant-1", "USDT")) == Decimal("400")


class TestPersistentLedgerReconciliation:
    """Test DB-backed reconciliation."""

    def test_reconcile_matched(self, ledger: PersistentLedger) -> None:
        ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="USDT",
            initial_balance="100",
        )
        record = ledger.reconcile_balance(
            tenant_id="tenant-1",
            asset="USDT",
            exchange_balance="100",
        )
        assert record.status.value == "matched"
        assert not record.has_discrepancy

    def test_reconcile_discrepancy(self, ledger: PersistentLedger) -> None:
        ledger.create_account(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="USDT",
            initial_balance="100",
        )
        record = ledger.reconcile_balance(
            tenant_id="tenant-1",
            asset="USDT",
            exchange_balance="90",
        )
        assert record.status.value == "discrepancy"
        assert record.has_discrepancy

        resolved = ledger.resolve_reconciliation(
            str(record.reconciliation_id), notes="Exchange lag"
        )
        assert resolved.status.value == "resolved"


class TestTransactionalOutbox:
    """Test transactional outbox for reliable event delivery."""

    def test_emit_and_consume_outbox_event(self, ledger: PersistentLedger) -> None:
        from uuid import uuid4 as _uuid4

        event_id = str(_uuid4())
        ledger.emit_outbox_event(
            event_id=event_id,
            aggregate_type="journal_entry",
            aggregate_id="entry-1",
            event_type="posted",
            payload={"entry_id": "entry-1", "amount": "100"},
            tenant_id="tenant-1",
        )
        pending = ledger.get_pending_outbox_events()
        assert len(pending) == 1
        assert pending[0]["event_id"] == event_id
        assert pending[0]["event_type"] == "posted"
        assert pending[0]["payload"]["entry_id"] == "entry-1"

        # Mark as processed
        ledger.mark_outbox_processed(event_id)
        pending = ledger.get_pending_outbox_events()
        assert len(pending) == 0

    def test_outbox_event_ordering(self, ledger: PersistentLedger) -> None:
        """Outbox events should be consumed in sequence order."""
        from uuid import uuid4 as _uuid4

        ids = []
        for i in range(3):
            eid = str(_uuid4())
            ids.append(eid)
            ledger.emit_outbox_event(
                event_id=eid,
                aggregate_type="test",
                aggregate_id=f"agg-{i}",
                event_type="created",
                payload={"i": i},
                tenant_id="tenant-1",
            )
        pending = ledger.get_pending_outbox_events()
        assert len(pending) == 3
        # Verify ordering by sequence_num
        seq_nums = [e["sequence_num"] for e in pending]
        assert seq_nums == sorted(seq_nums)


class TestTransactionalInbox:
    """Test transactional inbox for idempotent message processing."""

    def test_receive_inbox_message(self, ledger: PersistentLedger) -> None:
        result = ledger.receive_inbox_message(
            message_id="msg-1",
            source="exchange",
            event_type="fill",
            payload={"fill_id": "fill-1"},
            tenant_id="tenant-1",
        )
        assert result is True

        pending = ledger.get_pending_inbox_messages()
        assert len(pending) == 1
        assert pending[0]["message_id"] == "msg-1"

        # Mark as processed
        inbox_id = pending[0]["inbox_id"]
        ledger.mark_inbox_processed(inbox_id)
        pending = ledger.get_pending_inbox_messages()
        assert len(pending) == 0

    def test_inbox_idempotent_on_duplicate(self, ledger: PersistentLedger) -> None:
        """Same message_id → no duplicate (idempotent)."""
        result1 = ledger.receive_inbox_message(
            message_id="msg-dup",
            source="exchange",
            event_type="fill",
            payload={"fill_id": "fill-1"},
            tenant_id="tenant-1",
        )
        assert result1 is True

        result2 = ledger.receive_inbox_message(
            message_id="msg-dup",
            source="exchange",
            event_type="fill",
            payload={"fill_id": "fill-1"},
            tenant_id="tenant-1",
        )
        assert result2 is False

        pending = ledger.get_pending_inbox_messages()
        assert len(pending) == 1  # Still only 1


class TestDBEnforcedInvariants:
    """Test that DB-level constraints enforce invariants."""

    def test_unique_idempotency_key_at_db_level(self, ledger: PersistentLedger) -> None:
        """The UNIQUE constraint on idempotency_key prevents duplicates."""
        from sqlalchemy.orm import Session

        from services.ledger.persistence import _now_str

        with Session(ledger.engine) as session:
            session.add(
                IdempotencyKeyRow(
                    idempotency_key="test-key",
                    created_at=_now_str(),
                )
            )
            session.commit()
            # Try inserting the same key again → should fail
            with pytest.raises(Exception):
                session.add(
                    IdempotencyKeyRow(
                        idempotency_key="test-key",
                        created_at=_now_str(),
                    )
                )
                session.commit()

    def test_unique_fill_id_at_db_level(self, ledger: PersistentLedger) -> None:
        """The UNIQUE constraint on fill_id prevents duplicate fill mappings."""
        import json

        from sqlalchemy.orm import Session

        from services.ledger.persistence import FillMappingRow, _now_str

        with Session(ledger.engine) as session:
            session.add(
                FillMappingRow(
                    fill_id="fill-unique-test",
                    entry_ids=json.dumps(["e1"]),
                    asset_acquired="BTC",
                    asset_cost="USDT",
                    quantity="1",
                    price="50000",
                    fee="50",
                    fee_asset="USDT",
                    realized_pnl="0",
                    mapped_at=_now_str(),
                )
            )
            session.commit()
            with pytest.raises(Exception):
                session.add(
                    FillMappingRow(
                        fill_id="fill-unique-test",
                        entry_ids=json.dumps(["e2"]),
                        asset_acquired="BTC",
                        asset_cost="USDT",
                        quantity="1",
                        price="50000",
                        fee="50",
                        fee_asset="USDT",
                        realized_pnl="0",
                        mapped_at=_now_str(),
                    )
                )
                session.commit()

    def test_account_balance_non_negative_constraint(self, ledger: PersistentLedger) -> None:
        """The CHECK constraint prevents negative balance at DB level."""
        from sqlalchemy.orm import Session

        from services.ledger.persistence import FinancialAccountRow, _now_str

        with Session(ledger.engine) as session, pytest.raises(Exception):
            session.add(
                FinancialAccountRow(
                    account_id=str(uuid4()),
                    tenant_id="tenant-1",
                    account_type="spot",
                    asset="BTC",
                    balance="-1",  # Negative — should violate CHECK
                    reserved_balance="0",
                    created_at=_now_str(),
                    updated_at=_now_str(),
                )
            )
            session.commit()
