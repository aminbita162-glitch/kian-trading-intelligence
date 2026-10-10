"""Financial ledger contracts for Kian Trading Intelligence.

Per Section 07 (Financial Ledger and Profit Management):
- 07.1 Ledger Principles: durable transactional records, balanced financial
  postings, exact decimal arithmetic, asset-specific precision, idempotent
  processing, explicit correction entries, reconciliation checkpoints,
  traceable event provenance.
- 07.2 Financial Reporting: distinguish realized net P&L; unrealized P&L;
  available trading balance; reserved capital; profit-lock reservations;
  provider-reported withdrawable balance; open liabilities and unsettled
  amounts.
- 07.3 Profit Policies: multiple configurable thresholds for profit alerts;
  profit reservations; trading stop conditions; withdrawal-request
  preparation; financial review. Profit reservation is NOT a withdrawal.
- 07.4 Reconciliation: exchange-reported executions and balances must be
  reconciled with internal financial records. Silent ledger mutation is
  prohibited.

Per AD-018: durable, auditable financial records, balanced journal postings,
exact decimal arithmetic, idempotent accounting, and configurable profit
policies.

Per AD-007: realized net-profit calculations, configurable profit thresholds,
profit reservations, and controlled withdrawal-request workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

# ── Asset Precision ──

ASSET_PRECISION: dict[str, int] = {
    "BTC": 8,
    "ETH": 8,
    "USDT": 2,
    "USD": 2,
    "USDC": 2,
    "BNB": 8,
    "SOL": 8,
}

DEFAULT_PRECISION = 8


def get_precision(asset: str) -> int:
    """Get decimal precision for an asset symbol."""
    return ASSET_PRECISION.get(asset.upper(), DEFAULT_PRECISION)


def quantize(value: Decimal | str, asset: str) -> Decimal:
    """Quantize a value to the asset's precision using ROUND_HALF_UP."""
    precision = get_precision(asset)
    quant = Decimal(10) ** (-precision)
    return Decimal(str(value)).quantize(quant)


# ── Enums ──


class AccountType(StrEnum):
    """Type of financial account per Section 07.1."""

    SPOT = "spot"
    MARGIN = "margin"
    FUNDING = "funding"


class AccountSide(StrEnum):
    """Debit/Credit side for double-entry bookkeeping.

    Per Section 07.1: balanced financial postings.
    """

    DEBIT = "debit"
    CREDIT = "credit"


class JournalEntryType(StrEnum):
    """Type of journal entry for traceable event provenance.

    Per Section 07.1: traceable event provenance and explicit correction
    entries.
    """

    TRADE_EXECUTION = "trade_execution"
    FEE_ACCRUAL = "fee_accrual"
    FUNDING_DEPOSIT = "funding_deposit"
    FUNDING_WITHDRAWAL = "funding_withdrawal"
    REALIZED_PROFIT = "realized_profit"
    REALIZED_LOSS = "realized_loss"
    UNREALIZED_PROFIT = "unrealized_profit"
    UNREALIZED_LOSS = "unrealized_loss"
    CORRECTION = "correction"
    RESERVATION = "reservation"
    RESERVATION_RELEASE = "reservation_release"


class ProfitThresholdType(StrEnum):
    """Type of profit threshold per Section 07.3.

    Per AD-007: configurable profit thresholds for alerts, reservations,
    trading stop conditions, withdrawal-request preparation, and financial
    review.
    """

    PROFIT_ALERT = "profit_alert"
    PROFIT_RESERVATION = "profit_reservation"
    TRADING_STOP = "trading_stop"
    WITHDRAWAL_PREPARATION = "withdrawal_preparation"
    FINANCIAL_REVIEW = "financial_review"


class ReservationStatus(StrEnum):
    """Status of a profit reservation (distinct from risk reservation).

    Per Section 07.3: profit reservation is NOT a withdrawal. Actual
    withdrawals require separate authorization and provider/legal eligibility.
    """

    ACTIVE = "active"
    RELEASED = "released"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class WithdrawalStatus(StrEnum):
    """Status of a withdrawal request per AD-007.

    Per Section 07.3: actual withdrawals require separate authorization and
    provider/legal eligibility.
    """

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReconciliationStatus(StrEnum):
    """Status of a reconciliation between exchange and ledger.

    Per Section 07.4: exchange-reported executions and balances must be
    reconciled with internal financial records.
    """

    MATCHED = "matched"
    DISCREPANCY = "discrepancy"
    RESOLVED = "resolved"


# ── Stable Identity Value Objects ──


@dataclass(frozen=True)
class AccountId:
    """Stable identity for a financial account."""

    value: UUID

    @classmethod
    def generate(cls) -> AccountId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class JournalEntryId:
    """Stable identity for a journal entry.

    Per Section 07.1: idempotent processing — each entry has a stable
    identity that prevents duplicate postings.
    """

    value: UUID

    @classmethod
    def generate(cls) -> JournalEntryId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ProfitThresholdId:
    """Stable identity for a profit threshold configuration."""

    value: UUID

    @classmethod
    def generate(cls) -> ProfitThresholdId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ProfitReservationId:
    """Stable identity for a profit reservation.

    Per Section 07.3: profit reservation is NOT a withdrawal.
    """

    value: UUID

    @classmethod
    def generate(cls) -> ProfitReservationId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class WithdrawalRequestId:
    """Stable identity for a withdrawal request.

    Per AD-007: controlled withdrawal-request workflows.
    """

    value: UUID

    @classmethod
    def generate(cls) -> WithdrawalRequestId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ReconciliationId:
    """Stable identity for a reconciliation checkpoint."""

    value: UUID

    @classmethod
    def generate(cls) -> ReconciliationId:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


# ── Financial Account ──


@dataclass
class FinancialAccount:
    """Financial account model per Section 07.1.

    A financial account tracks the balance of a specific asset for a tenant.
    Each account has a type (spot, margin, funding) and tracks available
    and reserved balances.

    Per AD-018: durable, auditable financial records with exact decimal
    arithmetic.

    Attributes:
        account_id: Stable unique identifier.
        tenant_id: Tenant scope.
        account_type: Type of account (spot, margin, funding).
        asset: Asset symbol (e.g., "BTC", "USDT").
        balance: Current available balance.
        reserved_balance: Balance reserved by profit-lock reservations.
        created_at: UTC creation timestamp.
        updated_at: UTC last update timestamp.
    """

    account_id: AccountId
    tenant_id: str
    account_type: AccountType
    asset: str
    balance: str = "0"
    reserved_balance: str = "0"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.asset:
            raise ValueError("asset must not be empty.")
        if Decimal(self.balance) < 0:
            raise ValueError("balance must be non-negative.")
        if Decimal(self.reserved_balance) < 0:
            raise ValueError("reserved_balance must be non-negative.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware (UTC).")

    @property
    def available_balance(self) -> str:
        """Available balance = balance - reserved_balance.

        Per Section 07.2: distinguish available trading balance from
        reserved capital.
        """
        return str(Decimal(self.balance) - Decimal(self.reserved_balance))

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        account_type: AccountType,
        asset: str,
        initial_balance: str = "0",
    ) -> FinancialAccount:
        """Create a new financial account."""
        return cls(
            account_id=AccountId.generate(),
            tenant_id=tenant_id,
            account_type=account_type,
            asset=asset,
            balance=initial_balance,
            reserved_balance="0",
        )


# ── Journal Entry (Double-Entry) ──


@dataclass
class JournalLine:
    """A single line in a double-entry journal posting.

    Per Section 07.1: balanced financial postings — every entry has equal
    debits and credits. Each line is either a debit or credit to a
    specific account.

    For multi-asset ledgers, the ``value`` field (in a common quote
    currency, e.g., USDT) is used for balance validation. When all lines
    in an entry share the same asset, ``value`` defaults to ``amount``.

    Attributes:
        account_id: Target account.
        side: DEBIT or CREDIT.
        amount: Quantity to post in the line's asset (always positive).
        asset: Asset denomination.
        value: Value in a common quote currency for balance validation.
            Defaults to ``amount`` if not provided.
    """

    account_id: AccountId
    side: AccountSide
    amount: str
    asset: str
    value: str = ""

    def __post_init__(self) -> None:
        if Decimal(self.amount) <= 0:
            raise ValueError("Journal line amount must be positive.")
        if not self.asset:
            raise ValueError("asset must not be empty.")
        # Default value to amount if not specified
        if not self.value:
            object.__setattr__(self, "value", self.amount)


@dataclass
class JournalEntry:
    """A balanced double-entry journal posting.

    Per Section 07.1: balanced financial postings, idempotent processing,
    explicit correction entries, and traceable event provenance.

    Every entry must have equal total debits and total credits across all
    lines. The entry is immutable once posted — corrections use explicit
    CORRECTION entries.

    Attributes:
        entry_id: Stable unique identifier (idempotency key).
        tenant_id: Tenant scope.
        entry_type: Type of journal entry.
        lines: List of journal lines (must balance).
        reference: External reference (e.g., fill_id, order_id).
        description: Human-readable description.
        idempotency_key: Optional key for idempotent processing.
        created_at: UTC creation timestamp.
        posted_at: UTC posting timestamp (None if not yet posted).
    """

    entry_id: JournalEntryId
    tenant_id: str
    entry_type: JournalEntryType
    lines: list[JournalLine]
    reference: str = ""
    description: str = ""
    idempotency_key: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    posted_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("Journal entry must have at least one line.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        self._validate_balance()

    def _validate_balance(self) -> None:
        """Validate that debit values equal credit values.

        Per Section 07.1: balanced financial postings. For multi-asset
        entries, the ``value`` field (in a common quote currency) is
        used for balance validation.
        """
        debits = sum(
            (Decimal(line.value) for line in self.lines if line.side is AccountSide.DEBIT),
            Decimal(0),
        )
        credits = sum(
            (Decimal(line.value) for line in self.lines if line.side is AccountSide.CREDIT),
            Decimal(0),
        )
        if debits != credits:
            raise ValueError(
                f"Unbalanced journal entry: debits={debits}, credits={credits}. "
                "Debit values must equal credit values."
            )

    @property
    def is_balanced(self) -> bool:
        """True if debit values equal credit values."""
        debits = sum(
            (Decimal(line.value) for line in self.lines if line.side is AccountSide.DEBIT),
            Decimal(0),
        )
        credits = sum(
            (Decimal(line.value) for line in self.lines if line.side is AccountSide.CREDIT),
            Decimal(0),
        )
        return debits == credits

    @property
    def is_posted(self) -> bool:
        """True if the entry has been posted."""
        return self.posted_at is not None


# ── Fill-to-Ledger Mapping ──


@dataclass
class FillLedgerMapping:
    """Maps a fill to its corresponding journal entries.

    Per Section 07.1: traceable event provenance — every fill that affects
    the ledger must be traceable to the journal entries it generated.

    Attributes:
        fill_id: Fill identifier from the exchange.
        entry_ids: List of journal entry IDs generated for this fill.
        asset_acquired: Asset acquired (for buy) or disposed (for sell).
        asset_cost: Quote asset used for cost.
        quantity: Fill quantity.
        price: Fill price.
        fee: Fee charged.
        fee_asset: Asset in which fee is denominated.
        realized_pnl: Realized P&L for this fill (0 if no position was closed).
        mapped_at: UTC mapping timestamp.
    """

    fill_id: str
    entry_ids: list[str]
    asset_acquired: str
    asset_cost: str
    quantity: str
    price: str
    fee: str
    fee_asset: str
    realized_pnl: str = "0"
    mapped_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.fill_id:
            raise ValueError("fill_id must not be empty.")
        if Decimal(self.quantity) <= 0:
            raise ValueError("quantity must be positive.")
        if Decimal(self.price) <= 0:
            raise ValueError("price must be positive.")
        if Decimal(self.fee) < 0:
            raise ValueError("fee must be non-negative.")
        if self.mapped_at.tzinfo is None:
            raise ValueError("mapped_at must be timezone-aware (UTC).")


# ── P&L (Realized and Unrealized) ──


@dataclass
class ProfitLoss:
    """Realized or unrealized P&L calculation.

    Per Section 07.2: distinguish realized net P&L from unrealized P&L.

    Attributes:
        tenant_id: Tenant scope.
        realized_pnl: Total realized P&L (closed positions).
        unrealized_pnl: Total unrealized P&L (open positions).
        total_pnl: realized + unrealized.
        calculated_at: UTC calculation timestamp.
    """

    tenant_id: str
    realized_pnl: str = "0"
    unrealized_pnl: str = "0"
    calculated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.calculated_at.tzinfo is None:
            raise ValueError("calculated_at must be timezone-aware (UTC).")

    @property
    def total_pnl(self) -> str:
        """Total P&L = realized + unrealized."""
        return str(Decimal(self.realized_pnl) + Decimal(self.unrealized_pnl))


# ── Profit Threshold ──


@dataclass
class ProfitThreshold:
    """Configurable profit threshold per Section 07.3.

    Per AD-007: configurable profit thresholds for alerts, reservations,
    trading stop conditions, withdrawal-request preparation, and financial
    review. Thresholds must not trigger duplicate financial effects.

    Attributes:
        threshold_id: Stable unique identifier.
        tenant_id: Tenant scope.
        threshold_type: Type of threshold action.
        asset: Asset the threshold applies to.
        threshold_value: Value that triggers the threshold.
        is_active: Whether the threshold is active.
        created_at: UTC creation timestamp.
    """

    threshold_id: ProfitThresholdId
    tenant_id: str
    threshold_type: ProfitThresholdType
    asset: str
    threshold_value: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.asset:
            raise ValueError("asset must not be empty.")
        if Decimal(self.threshold_value) <= 0:
            raise ValueError("threshold_value must be positive.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        threshold_type: ProfitThresholdType,
        asset: str,
        threshold_value: str,
    ) -> ProfitThreshold:
        """Create a new active profit threshold."""
        return cls(
            threshold_id=ProfitThresholdId.generate(),
            tenant_id=tenant_id,
            threshold_type=threshold_type,
            asset=asset,
            threshold_value=threshold_value,
            is_active=True,
        )


# ── Profit Reservation ──


@dataclass
class ProfitReservationEntry:
    """A profit reservation entry per Section 07.3.

    Per Section 07.3: profit reservation is NOT a withdrawal. Actual
    withdrawals require separate authorization and provider/legal
    eligibility.

    Attributes:
        reservation_id: Stable unique identifier.
        tenant_id: Tenant scope.
        asset: Reserved asset.
        reserved_amount: Amount reserved.
        threshold_type: Type of threshold that triggered the reservation.
        status: Reservation status.
        created_at: UTC creation timestamp.
        released_at: UTC release timestamp (None if still active).
    """

    reservation_id: ProfitReservationId
    tenant_id: str
    asset: str
    reserved_amount: str
    threshold_type: ProfitThresholdType
    status: ReservationStatus = ReservationStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.asset:
            raise ValueError("asset must not be empty.")
        if Decimal(self.reserved_amount) <= 0:
            raise ValueError("reserved_amount must be positive.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    @property
    def is_active(self) -> bool:
        """True if the reservation is active."""
        return self.status is ReservationStatus.ACTIVE

    def release(self) -> ProfitReservationEntry:
        """Release the reservation back to the available balance."""
        if self.status is not ReservationStatus.ACTIVE:
            raise ValueError(f"Cannot release reservation in status {self.status}.")
        return ProfitReservationEntry(
            reservation_id=self.reservation_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            reserved_amount=self.reserved_amount,
            threshold_type=self.threshold_type,
            status=ReservationStatus.RELEASED,
            created_at=self.created_at,
            released_at=datetime.now(UTC),
        )

    def consume(self) -> ProfitReservationEntry:
        """Consume the reservation (e.g., converted to withdrawal)."""
        if self.status is not ReservationStatus.ACTIVE:
            raise ValueError(f"Cannot consume reservation in status {self.status}.")
        return ProfitReservationEntry(
            reservation_id=self.reservation_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            reserved_amount=self.reserved_amount,
            threshold_type=self.threshold_type,
            status=ReservationStatus.CONSUMED,
            created_at=self.created_at,
            released_at=datetime.now(UTC),
        )


# ── Withdrawal Request ──


@dataclass
class WithdrawalRequest:
    """Withdrawal request contract per AD-007 and Section 07.3.

    Per Section 07.3: actual withdrawals require separate authorization
    and provider/legal eligibility. A profit reservation is NOT a withdrawal.

    Per AD-029: live functionality must respect jurisdiction, provider
    eligibility, account permissions, and applicable legal obligations.

    Attributes:
        request_id: Stable unique identifier.
        tenant_id: Tenant scope.
        asset: Asset to withdraw.
        amount: Withdrawal amount.
        destination_address: Target wallet address (if applicable).
        status: Withdrawal status lifecycle.
        created_at: UTC creation timestamp.
        approved_at: UTC approval timestamp (None if not approved).
        submitted_at: UTC submission timestamp (None if not submitted).
        completed_at: UTC completion timestamp (None if not completed).
        reason: Rejection/cancellation reason.
        provider_tx_id: Provider transaction ID (None until completed).
    """

    request_id: WithdrawalRequestId
    tenant_id: str
    asset: str
    amount: str
    destination_address: str = ""
    status: WithdrawalStatus = WithdrawalStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    reason: str = ""
    provider_tx_id: str | None = None

    def __post_init__(self) -> None:
        if not self.asset:
            raise ValueError("asset must not be empty.")
        if Decimal(self.amount) <= 0:
            raise ValueError("amount must be positive.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        asset: str,
        amount: str,
        destination_address: str = "",
    ) -> WithdrawalRequest:
        """Create a new withdrawal request in DRAFT status."""
        return cls(
            request_id=WithdrawalRequestId.generate(),
            tenant_id=tenant_id,
            asset=asset,
            amount=amount,
            destination_address=destination_address,
            status=WithdrawalStatus.DRAFT,
        )

    def approve(self) -> WithdrawalRequest:
        """Approve the withdrawal (requires explicit human authorization)."""
        if self.status is not WithdrawalStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Cannot approve withdrawal in status {self.status}. Must be PENDING_APPROVAL."
            )
        return WithdrawalRequest(
            request_id=self.request_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            amount=self.amount,
            destination_address=self.destination_address,
            status=WithdrawalStatus.APPROVED,
            created_at=self.created_at,
            approved_at=datetime.now(UTC),
        )

    def reject(self, reason: str = "") -> WithdrawalRequest:
        """Reject the withdrawal."""
        if self.status not in (WithdrawalStatus.DRAFT, WithdrawalStatus.PENDING_APPROVAL):
            raise ValueError(f"Cannot reject withdrawal in status {self.status}.")
        return WithdrawalRequest(
            request_id=self.request_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            amount=self.amount,
            destination_address=self.destination_address,
            status=WithdrawalStatus.REJECTED,
            created_at=self.created_at,
            approved_at=self.approved_at,
            reason=reason or "Withdrawal rejected",
        )

    def submit(self) -> WithdrawalRequest:
        """Submit the withdrawal to the provider."""
        if self.status is not WithdrawalStatus.APPROVED:
            raise ValueError(f"Cannot submit withdrawal in status {self.status}. Must be APPROVED.")
        return WithdrawalRequest(
            request_id=self.request_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            amount=self.amount,
            destination_address=self.destination_address,
            status=WithdrawalStatus.SUBMITTED,
            created_at=self.created_at,
            approved_at=self.approved_at,
            submitted_at=datetime.now(UTC),
        )

    def complete(self, provider_tx_id: str = "") -> WithdrawalRequest:
        """Mark the withdrawal as completed with provider confirmation."""
        if self.status is not WithdrawalStatus.SUBMITTED:
            raise ValueError(
                f"Cannot complete withdrawal in status {self.status}. Must be SUBMITTED."
            )
        return WithdrawalRequest(
            request_id=self.request_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            amount=self.amount,
            destination_address=self.destination_address,
            status=WithdrawalStatus.COMPLETED,
            created_at=self.created_at,
            approved_at=self.approved_at,
            submitted_at=self.submitted_at,
            completed_at=datetime.now(UTC),
            provider_tx_id=provider_tx_id or None,
        )

    def fail(self, reason: str = "") -> WithdrawalRequest:
        """Mark the withdrawal as failed."""
        if self.status not in (
            WithdrawalStatus.SUBMITTED,
            WithdrawalStatus.PENDING_APPROVAL,
        ):
            raise ValueError(f"Cannot fail withdrawal in status {self.status}.")
        return WithdrawalRequest(
            request_id=self.request_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            amount=self.amount,
            destination_address=self.destination_address,
            status=WithdrawalStatus.FAILED,
            created_at=self.created_at,
            approved_at=self.approved_at,
            submitted_at=self.submitted_at,
            reason=reason or "Withdrawal failed",
        )

    def cancel(self, reason: str = "") -> WithdrawalRequest:
        """Cancel the withdrawal."""
        if self.status in (WithdrawalStatus.COMPLETED, WithdrawalStatus.SUBMITTED):
            raise ValueError(
                f"Cannot cancel withdrawal in status {self.status}. "
                "Submitted or completed withdrawals cannot be cancelled."
            )
        return WithdrawalRequest(
            request_id=self.request_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            amount=self.amount,
            destination_address=self.destination_address,
            status=WithdrawalStatus.CANCELLED,
            created_at=self.created_at,
            approved_at=self.approved_at,
            submitted_at=self.submitted_at,
            reason=reason or "Withdrawal cancelled",
        )

    def submit_for_approval(self) -> WithdrawalRequest:
        """Submit the withdrawal for approval."""
        if self.status is not WithdrawalStatus.DRAFT:
            raise ValueError(f"Cannot submit for approval in status {self.status}. Must be DRAFT.")
        return WithdrawalRequest(
            request_id=self.request_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            amount=self.amount,
            destination_address=self.destination_address,
            status=WithdrawalStatus.PENDING_APPROVAL,
            created_at=self.created_at,
        )


# ── Reconciliation ──


@dataclass
class ReconciliationRecord:
    """A reconciliation record per Section 07.4.

    Per Section 07.4: exchange-reported executions and balances must be
    reconciled with internal financial records. Discrepancies must produce
    explicit incidents or correction workflows. Silent ledger mutation
    is prohibited.

    Attributes:
        reconciliation_id: Stable unique identifier.
        tenant_id: Tenant scope.
        asset: Asset being reconciled.
        ledger_balance: Internal ledger balance.
        exchange_balance: Exchange-reported balance.
        discrepancy: Difference between ledger and exchange.
        status: Reconciliation status.
        created_at: UTC creation timestamp.
        resolved_at: UTC resolution timestamp (None if unresolved).
        resolution_notes: Notes on how the discrepancy was resolved.
    """

    reconciliation_id: ReconciliationId
    tenant_id: str
    asset: str
    ledger_balance: str
    exchange_balance: str
    status: ReconciliationStatus = ReconciliationStatus.MATCHED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolution_notes: str = ""

    def __post_init__(self) -> None:
        if not self.asset:
            raise ValueError("asset must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (UTC).")
        # Only auto-determine status from balances if not explicitly resolved.
        # RESOLVED is a terminal state set by resolve(); it must not be
        # overwritten by the discrepancy check.
        if self.status is not ReconciliationStatus.RESOLVED:
            discrepancy = Decimal(self.ledger_balance) - Decimal(self.exchange_balance)
            if discrepancy == 0:
                object.__setattr__(self, "status", ReconciliationStatus.MATCHED)
            else:
                object.__setattr__(self, "status", ReconciliationStatus.DISCREPANCY)

    @property
    def discrepancy(self) -> str:
        """Discrepancy = ledger_balance - exchange_balance."""
        return str(Decimal(self.ledger_balance) - Decimal(self.exchange_balance))

    @property
    def has_discrepancy(self) -> bool:
        """True if there is a discrepancy between ledger and exchange."""
        return Decimal(self.discrepancy) != 0

    def resolve(self, notes: str = "") -> ReconciliationRecord:
        """Resolve the discrepancy with correction notes.

        Per Section 07.4: discrepancies must produce explicit correction
        workflows. Silent ledger mutation is prohibited.
        """
        if self.status is not ReconciliationStatus.DISCREPANCY:
            raise ValueError(
                f"Cannot resolve reconciliation in status {self.status}. Must be DISCREPANCY."
            )
        return ReconciliationRecord(
            reconciliation_id=self.reconciliation_id,
            tenant_id=self.tenant_id,
            asset=self.asset,
            ledger_balance=self.ledger_balance,
            exchange_balance=self.exchange_balance,
            status=ReconciliationStatus.RESOLVED,
            created_at=self.created_at,
            resolved_at=datetime.now(UTC),
            resolution_notes=notes or "Discrepancy resolved with correction entry.",
        )
