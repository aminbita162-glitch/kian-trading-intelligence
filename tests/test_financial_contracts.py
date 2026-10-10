"""Tests for financial ledger contracts (Phase 05).

Per Section 07 (Financial Ledger and Profit Management):
- 07.1: durable records, balanced postings, exact decimal arithmetic,
  asset-specific precision, idempotent processing, explicit corrections,
  reconciliation checkpoints, traceable provenance.
- 07.3: profit policies — thresholds, reservations, withdrawal-request
  contracts.

Per AD-018: balanced journal postings, exact decimal arithmetic, idempotent
accounting, configurable profit policies.
Per AD-007: realized net-profit, configurable thresholds, profit
reservations, controlled withdrawal-request workflows.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from contracts.ledger import (
    DEFAULT_PRECISION,
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
    WithdrawalStatus,
    get_precision,
    quantize,
)


class TestAccountType:
    """Tests for the AccountType enum."""

    def test_spot_type(self) -> None:
        assert AccountType.SPOT.value == "spot"

    def test_margin_type(self) -> None:
        assert AccountType.MARGIN.value == "margin"

    def test_funding_type(self) -> None:
        assert AccountType.FUNDING.value == "funding"

    def test_all_types_distinct(self) -> None:
        values = {t.value for t in AccountType}
        assert len(values) == 3


class TestAccountSide:
    """Tests for the AccountSide enum."""

    def test_debit(self) -> None:
        assert AccountSide.DEBIT.value == "debit"

    def test_credit(self) -> None:
        assert AccountSide.CREDIT.value == "credit"


class TestJournalEntryType:
    """Tests for the JournalEntryType enum."""

    def test_trade_execution(self) -> None:
        assert JournalEntryType.TRADE_EXECUTION.value == "trade_execution"

    def test_fee_accrual(self) -> None:
        assert JournalEntryType.FEE_ACCRUAL.value == "fee_accrual"

    def test_correction(self) -> None:
        assert JournalEntryType.CORRECTION.value == "correction"

    def test_reservation(self) -> None:
        assert JournalEntryType.RESERVATION.value == "reservation"

    def test_all_types(self) -> None:
        types = {t.value for t in JournalEntryType}
        assert "trade_execution" in types
        assert "fee_accrual" in types
        assert "correction" in types
        assert len(types) >= 10


class TestProfitThresholdType:
    """Tests for the ProfitThresholdType enum."""

    def test_profit_alert(self) -> None:
        assert ProfitThresholdType.PROFIT_ALERT.value == "profit_alert"

    def test_profit_reservation(self) -> None:
        assert ProfitThresholdType.PROFIT_RESERVATION.value == "profit_reservation"

    def test_trading_stop(self) -> None:
        assert ProfitThresholdType.TRADING_STOP.value == "trading_stop"

    def test_withdrawal_preparation(self) -> None:
        assert ProfitThresholdType.WITHDRAWAL_PREPARATION.value == "withdrawal_preparation"

    def test_financial_review(self) -> None:
        assert ProfitThresholdType.FINANCIAL_REVIEW.value == "financial_review"


class TestReservationStatus:
    """Tests for the ReservationStatus enum."""

    def test_active(self) -> None:
        assert ReservationStatus.ACTIVE.value == "active"

    def test_released(self) -> None:
        assert ReservationStatus.RELEASED.value == "released"

    def test_consumed(self) -> None:
        assert ReservationStatus.CONSUMED.value == "consumed"

    def test_expired(self) -> None:
        assert ReservationStatus.EXPIRED.value == "expired"


class TestWithdrawalStatus:
    """Tests for the WithdrawalStatus enum."""

    def test_draft(self) -> None:
        assert WithdrawalStatus.DRAFT.value == "draft"

    def test_pending_approval(self) -> None:
        assert WithdrawalStatus.PENDING_APPROVAL.value == "pending_approval"

    def test_approved(self) -> None:
        assert WithdrawalStatus.APPROVED.value == "approved"

    def test_rejected(self) -> None:
        assert WithdrawalStatus.REJECTED.value == "rejected"

    def test_submitted(self) -> None:
        assert WithdrawalStatus.SUBMITTED.value == "submitted"

    def test_completed(self) -> None:
        assert WithdrawalStatus.COMPLETED.value == "completed"

    def test_failed(self) -> None:
        assert WithdrawalStatus.FAILED.value == "failed"

    def test_cancelled(self) -> None:
        assert WithdrawalStatus.CANCELLED.value == "cancelled"


class TestReconciliationStatus:
    """Tests for the ReconciliationStatus enum."""

    def test_matched(self) -> None:
        assert ReconciliationStatus.MATCHED.value == "matched"

    def test_discrepancy(self) -> None:
        assert ReconciliationStatus.DISCREPANCY.value == "discrepancy"

    def test_resolved(self) -> None:
        assert ReconciliationStatus.RESOLVED.value == "resolved"


class TestAssetPrecision:
    """Tests for asset-specific precision (Section 07.1)."""

    def test_btc_precision(self) -> None:
        assert get_precision("BTC") == 8

    def test_usdt_precision(self) -> None:
        assert get_precision("USDT") == 2

    def test_usd_precision(self) -> None:
        assert get_precision("USD") == 2

    def test_default_precision(self) -> None:
        assert DEFAULT_PRECISION == 8

    def test_unknown_asset_defaults(self) -> None:
        assert get_precision("UNKNOWN") == DEFAULT_PRECISION

    def test_quantize_btc(self) -> None:
        result = quantize(Decimal("1.123456789"), "BTC")
        assert result == Decimal("1.12345679")

    def test_quantize_usdt(self) -> None:
        result = quantize(Decimal("1.123456789"), "USDT")
        assert result == Decimal("1.12")


class TestFinancialAccount:
    """Tests for the FinancialAccount contract (Section 07.1)."""

    def test_create_account(self) -> None:
        account = FinancialAccount.create(
            tenant_id="tenant-1",
            account_type=AccountType.SPOT,
            asset="BTC",
            initial_balance="100.0",
        )
        assert account.tenant_id == "tenant-1"
        assert account.account_type is AccountType.SPOT
        assert account.asset == "BTC"
        assert account.balance == "100.0"
        assert account.reserved_balance == "0"

    def test_available_balance(self) -> None:
        account = FinancialAccount.create(
            tenant_id="t1",
            account_type=AccountType.SPOT,
            asset="USDT",
            initial_balance="1000.00",
        )
        # Need to manually set reserved_balance for this test
        account2 = FinancialAccount(
            account_id=account.account_id,
            tenant_id="t1",
            account_type=AccountType.SPOT,
            asset="USDT",
            balance="1000.00",
            reserved_balance="200.00",
        )
        assert Decimal(account2.available_balance) == Decimal("800.00")

    def test_negative_balance_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            FinancialAccount(
                account_id=AccountId.generate(),
                tenant_id="t1",
                account_type=AccountType.SPOT,
                asset="BTC",
                balance="-100",
            )

    def test_negative_reserved_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            FinancialAccount(
                account_id=AccountId.generate(),
                tenant_id="t1",
                account_type=AccountType.SPOT,
                asset="BTC",
                balance="100",
                reserved_balance="-50",
            )

    def test_empty_asset_rejected(self) -> None:
        with pytest.raises(ValueError, match="asset"):
            FinancialAccount(
                account_id=AccountId.generate(),
                tenant_id="t1",
                account_type=AccountType.SPOT,
                asset="",
            )

    def test_timezone_aware_required(self) -> None:
        naive = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(ValueError, match="timezone-aware"):
            FinancialAccount(
                account_id=AccountId.generate(),
                tenant_id="t1",
                account_type=AccountType.SPOT,
                asset="BTC",
                created_at=naive,
            )


class TestJournalLine:
    """Tests for JournalLine — double-entry bookkeeping."""

    def test_valid_debit_line(self) -> None:
        line = JournalLine(
            account_id=AccountId.generate(),
            side=AccountSide.DEBIT,
            amount="100.00",
            asset="USDT",
        )
        assert Decimal(line.amount) == Decimal("100.00")

    def test_valid_credit_line(self) -> None:
        line = JournalLine(
            account_id=AccountId.generate(),
            side=AccountSide.CREDIT,
            amount="50.00",
            asset="USDT",
        )
        assert Decimal(line.amount) == Decimal("50.00")

    def test_zero_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            JournalLine(
                account_id=AccountId.generate(),
                side=AccountSide.DEBIT,
                amount="0",
                asset="USDT",
            )

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            JournalLine(
                account_id=AccountId.generate(),
                side=AccountSide.DEBIT,
                amount="-50",
                asset="USDT",
            )

    def test_empty_asset_rejected(self) -> None:
        with pytest.raises(ValueError, match="asset"):
            JournalLine(
                account_id=AccountId.generate(),
                side=AccountSide.DEBIT,
                amount="100",
                asset="",
            )


class TestJournalEntry:
    """Tests for JournalEntry — balanced double-entry (Section 07.1)."""

    def _make_account(self) -> AccountId:
        return AccountId.generate()

    def test_balanced_entry(self) -> None:
        aid1 = self._make_account()
        aid2 = self._make_account()
        entry = JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id="t1",
            entry_type=JournalEntryType.TRADE_EXECUTION,
            lines=[
                JournalLine(account_id=aid1, side=AccountSide.DEBIT, amount="100.00", asset="USDT"),
                JournalLine(
                    account_id=aid2, side=AccountSide.CREDIT, amount="100.00", asset="USDT"
                ),
            ],
        )
        assert entry.is_balanced

    def test_unbalanced_entry_rejected(self) -> None:
        aid1 = AccountId.generate()
        aid2 = AccountId.generate()
        with pytest.raises(ValueError, match="Unbalanced"):
            JournalEntry(
                entry_id=JournalEntryId.generate(),
                tenant_id="t1",
                entry_type=JournalEntryType.TRADE_EXECUTION,
                lines=[
                    JournalLine(
                        account_id=aid1, side=AccountSide.DEBIT, amount="100.00", asset="USDT"
                    ),
                    JournalLine(
                        account_id=aid2, side=AccountSide.CREDIT, amount="50.00", asset="USDT"
                    ),
                ],
            )

    def test_empty_lines_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one line"):
            JournalEntry(
                entry_id=JournalEntryId.generate(),
                tenant_id="t1",
                entry_type=JournalEntryType.TRADE_EXECUTION,
                lines=[],
            )

    def test_is_posted_initially_false(self) -> None:
        aid = AccountId.generate()
        entry = JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id="t1",
            entry_type=JournalEntryType.TRADE_EXECUTION,
            lines=[
                JournalLine(account_id=aid, side=AccountSide.DEBIT, amount="100.00", asset="USDT"),
                JournalLine(account_id=aid, side=AccountSide.CREDIT, amount="100.00", asset="USDT"),
            ],
        )
        assert not entry.is_posted

    def test_timezone_aware_required(self) -> None:
        naive = datetime(2024, 1, 1, 12, 0, 0)
        aid = AccountId.generate()
        with pytest.raises(ValueError, match="timezone-aware"):
            JournalEntry(
                entry_id=JournalEntryId.generate(),
                tenant_id="t1",
                entry_type=JournalEntryType.TRADE_EXECUTION,
                lines=[
                    JournalLine(
                        account_id=aid, side=AccountSide.DEBIT, amount="100.00", asset="USDT"
                    ),
                    JournalLine(
                        account_id=aid, side=AccountSide.CREDIT, amount="100.00", asset="USDT"
                    ),
                ],
                created_at=naive,
            )


class TestProfitThreshold:
    """Tests for ProfitThreshold contracts (Section 07.3)."""

    def test_create_threshold(self) -> None:
        threshold = ProfitThreshold.create(
            tenant_id="t1",
            threshold_type=ProfitThresholdType.PROFIT_ALERT,
            asset="USDT",
            threshold_value="1000.00",
        )
        assert threshold.tenant_id == "t1"
        assert threshold.threshold_type is ProfitThresholdType.PROFIT_ALERT
        assert threshold.asset == "USDT"
        assert threshold.is_active

    def test_zero_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ProfitThreshold(
                threshold_id=ProfitThresholdId.generate(),
                tenant_id="t1",
                threshold_type=ProfitThresholdType.PROFIT_ALERT,
                asset="USDT",
                threshold_value="0",
            )

    def test_empty_asset_rejected(self) -> None:
        with pytest.raises(ValueError, match="asset"):
            ProfitThreshold(
                threshold_id=ProfitThresholdId.generate(),
                tenant_id="t1",
                threshold_type=ProfitThresholdType.PROFIT_ALERT,
                asset="",
                threshold_value="100",
            )


class TestProfitReservationEntry:
    """Tests for ProfitReservationEntry (Section 07.3)."""

    def test_create_reservation(self) -> None:
        reservation = ProfitReservationEntry(
            reservation_id=ProfitReservationId.generate(),
            tenant_id="t1",
            asset="USDT",
            reserved_amount="500.00",
            threshold_type=ProfitThresholdType.PROFIT_RESERVATION,
        )
        assert reservation.is_active
        assert Decimal(reservation.reserved_amount) == Decimal("500.00")

    def test_release_reservation(self) -> None:
        reservation = ProfitReservationEntry(
            reservation_id=ProfitReservationId.generate(),
            tenant_id="t1",
            asset="USDT",
            reserved_amount="500.00",
            threshold_type=ProfitThresholdType.PROFIT_RESERVATION,
        )
        released = reservation.release()
        assert not released.is_active
        assert released.status is ReservationStatus.RELEASED
        assert released.released_at is not None

    def test_consume_reservation(self) -> None:
        reservation = ProfitReservationEntry(
            reservation_id=ProfitReservationId.generate(),
            tenant_id="t1",
            asset="USDT",
            reserved_amount="500.00",
            threshold_type=ProfitThresholdType.PROFIT_RESERVATION,
        )
        consumed = reservation.consume()
        assert consumed.status is ReservationStatus.CONSUMED

    def test_release_non_active_rejected(self) -> None:
        reservation = ProfitReservationEntry(
            reservation_id=ProfitReservationId.generate(),
            tenant_id="t1",
            asset="USDT",
            reserved_amount="500.00",
            threshold_type=ProfitThresholdType.PROFIT_RESERVATION,
        )
        released = reservation.release()
        with pytest.raises(ValueError, match="Cannot release"):
            released.release()

    def test_zero_reserved_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ProfitReservationEntry(
                reservation_id=ProfitReservationId.generate(),
                tenant_id="t1",
                asset="USDT",
                reserved_amount="0",
                threshold_type=ProfitThresholdType.PROFIT_RESERVATION,
            )


class TestWithdrawalRequest:
    """Tests for WithdrawalRequest contracts (AD-007, Section 07.3)."""

    def test_create_withdrawal(self) -> None:
        req = WithdrawalRequest.create(
            tenant_id="t1",
            asset="USDT",
            amount="100.00",
        )
        assert req.status is WithdrawalStatus.DRAFT
        assert Decimal(req.amount) == Decimal("100.00")

    def test_full_lifecycle(self) -> None:
        req = WithdrawalRequest.create(
            tenant_id="t1",
            asset="USDT",
            amount="100.00",
        )
        pending = req.submit_for_approval()
        assert pending.status is WithdrawalStatus.PENDING_APPROVAL

        approved = pending.approve()
        assert approved.status is WithdrawalStatus.APPROVED
        assert approved.approved_at is not None

        submitted = approved.submit()
        assert submitted.status is WithdrawalStatus.SUBMITTED
        assert submitted.submitted_at is not None

        completed = submitted.complete("tx-123")
        assert completed.status is WithdrawalStatus.COMPLETED
        assert completed.completed_at is not None
        assert completed.provider_tx_id == "tx-123"

    def test_reject_from_pending(self) -> None:
        req = WithdrawalRequest.create(
            tenant_id="t1",
            asset="USDT",
            amount="100.00",
        )
        pending = req.submit_for_approval()
        rejected = pending.reject("Not eligible")
        assert rejected.status is WithdrawalStatus.REJECTED
        assert "Not eligible" in rejected.reason

    def test_cancel_from_draft(self) -> None:
        req = WithdrawalRequest.create(
            tenant_id="t1",
            asset="USDT",
            amount="100.00",
        )
        cancelled = req.cancel("User cancelled")
        assert cancelled.status is WithdrawalStatus.CANCELLED

    def test_cannot_cancel_completed(self) -> None:
        req = WithdrawalRequest.create(
            tenant_id="t1",
            asset="USDT",
            amount="100.00",
        )
        pending = req.submit_for_approval()
        approved = pending.approve()
        submitted = approved.submit()
        completed = submitted.complete("tx-1")
        with pytest.raises(ValueError, match="Cannot cancel"):
            completed.cancel()

    def test_cannot_submit_unapproved(self) -> None:
        req = WithdrawalRequest.create(
            tenant_id="t1",
            asset="USDT",
            amount="100.00",
        )
        with pytest.raises(ValueError, match="Cannot submit"):
            req.submit()

    def test_cannot_approve_draft(self) -> None:
        req = WithdrawalRequest.create(
            tenant_id="t1",
            asset="USDT",
            amount="100.00",
        )
        with pytest.raises(ValueError, match="Cannot approve"):
            req.approve()

    def test_fail_from_submitted(self) -> None:
        req = WithdrawalRequest.create(
            tenant_id="t1",
            asset="USDT",
            amount="100.00",
        )
        pending = req.submit_for_approval()
        approved = pending.approve()
        submitted = approved.submit()
        failed = submitted.fail("Provider error")
        assert failed.status is WithdrawalStatus.FAILED
        assert "Provider error" in failed.reason

    def test_zero_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            WithdrawalRequest.create(
                tenant_id="t1",
                asset="USDT",
                amount="0",
            )

    def test_empty_asset_rejected(self) -> None:
        with pytest.raises(ValueError, match="asset"):
            WithdrawalRequest.create(
                tenant_id="t1",
                asset="",
                amount="100",
            )


class TestReconciliationRecord:
    """Tests for ReconciliationRecord contracts (Section 07.4)."""

    def test_matched_record(self) -> None:
        record = ReconciliationRecord(
            reconciliation_id=ReconciliationId.generate(),
            tenant_id="t1",
            asset="USDT",
            ledger_balance="1000.00",
            exchange_balance="1000.00",
        )
        assert record.status is ReconciliationStatus.MATCHED
        assert not record.has_discrepancy
        assert Decimal(record.discrepancy) == Decimal(0)

    def test_discrepancy_record(self) -> None:
        record = ReconciliationRecord(
            reconciliation_id=ReconciliationId.generate(),
            tenant_id="t1",
            asset="USDT",
            ledger_balance="1000.00",
            exchange_balance="900.00",
        )
        assert record.status is ReconciliationStatus.DISCREPANCY
        assert record.has_discrepancy
        assert Decimal(record.discrepancy) == Decimal("100.00")

    def test_resolve_discrepancy(self) -> None:
        record = ReconciliationRecord(
            reconciliation_id=ReconciliationId.generate(),
            tenant_id="t1",
            asset="USDT",
            ledger_balance="1000.00",
            exchange_balance="900.00",
        )
        resolved = record.resolve("Correction posted")
        assert resolved.status is ReconciliationStatus.RESOLVED
        assert resolved.resolved_at is not None
        assert "Correction posted" in resolved.resolution_notes

    def test_cannot_resolve_matched(self) -> None:
        record = ReconciliationRecord(
            reconciliation_id=ReconciliationId.generate(),
            tenant_id="t1",
            asset="USDT",
            ledger_balance="1000.00",
            exchange_balance="1000.00",
        )
        with pytest.raises(ValueError, match="Cannot resolve"):
            record.resolve()

    def test_empty_asset_rejected(self) -> None:
        with pytest.raises(ValueError, match="asset"):
            ReconciliationRecord(
                reconciliation_id=ReconciliationId.generate(),
                tenant_id="t1",
                asset="",
                ledger_balance="100",
                exchange_balance="100",
            )


class TestFillLedgerMapping:
    """Tests for FillLedgerMapping (Section 07.1)."""

    def test_valid_mapping(self) -> None:
        mapping = FillLedgerMapping(
            fill_id="fill-001",
            entry_ids=["entry-001", "entry-002"],
            asset_acquired="BTC",
            asset_cost="USDT",
            quantity="1.5",
            price="50000.00",
            fee="10.00",
            fee_asset="USDT",
        )
        assert mapping.fill_id == "fill-001"
        assert len(mapping.entry_ids) == 2

    def test_zero_quantity_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            FillLedgerMapping(
                fill_id="fill-001",
                entry_ids=["e1"],
                asset_acquired="BTC",
                asset_cost="USDT",
                quantity="0",
                price="50000",
                fee="0",
                fee_asset="USDT",
            )

    def test_zero_price_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            FillLedgerMapping(
                fill_id="fill-001",
                entry_ids=["e1"],
                asset_acquired="BTC",
                asset_cost="USDT",
                quantity="1",
                price="0",
                fee="0",
                fee_asset="USDT",
            )

    def test_negative_fee_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            FillLedgerMapping(
                fill_id="fill-001",
                entry_ids=["e1"],
                asset_acquired="BTC",
                asset_cost="USDT",
                quantity="1",
                price="50000",
                fee="-10",
                fee_asset="USDT",
            )

    def test_empty_fill_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="fill_id"):
            FillLedgerMapping(
                fill_id="",
                entry_ids=["e1"],
                asset_acquired="BTC",
                asset_cost="USDT",
                quantity="1",
                price="50000",
                fee="0",
                fee_asset="USDT",
            )


class TestProfitLoss:
    """Tests for ProfitLoss (Section 07.2)."""

    def test_total_pnl(self) -> None:
        pnl = ProfitLoss(
            tenant_id="t1",
            realized_pnl="500.00",
            unrealized_pnl="200.00",
        )
        assert Decimal(pnl.total_pnl) == Decimal("700.00")

    def test_zero_pnl(self) -> None:
        pnl = ProfitLoss(tenant_id="t1")
        assert Decimal(pnl.total_pnl) == Decimal(0)

    def test_negative_pnl(self) -> None:
        pnl = ProfitLoss(
            tenant_id="t1",
            realized_pnl="-300.00",
            unrealized_pnl="-100.00",
        )
        assert Decimal(pnl.total_pnl) == Decimal("-400.00")
