"""Financial ledger service for Kian Trading Intelligence.

Per Section 07 (Financial Ledger and Profit Management):
- 07.1: durable transactional records, balanced postings, exact decimal
  arithmetic, asset-specific precision, idempotent processing, explicit
  corrections, reconciliation checkpoints, traceable provenance.
- 07.2: financial reporting — realized P&L, unrealized P&L, available
  balance, reserved capital, profit-lock reservations, provider-reported
  withdrawable balance, open liabilities.
- 07.3: profit policies — configurable thresholds, profit reservations,
  trading stop conditions, withdrawal-request preparation, financial review.
- 07.4: reconciliation — exchange-reported balances reconciled with
  internal records; silent mutation prohibited.

Per AD-018: balanced journal postings, exact decimal arithmetic, idempotent
accounting, configurable profit policies.
Per AD-007: realized net-profit, configurable thresholds, profit
reservations, controlled withdrawal-request workflows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from threading import Lock

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
    ProfitThresholdType,
    ReconciliationId,
    ReconciliationRecord,
    WithdrawalRequest,
    quantize,
)
from contracts.ledger import (
    ProfitThresholdId as ProfitThresholdId,
)
from contracts.ledger import (
    ReconciliationStatus as ReconciliationStatus,
)
from contracts.ledger import (
    ReservationStatus as ReservationStatus,
)
from contracts.ledger import (
    WithdrawalRequestId as WithdrawalRequestId,
)
from contracts.ledger import (
    WithdrawalStatus as WithdrawalStatus,
)


class LedgerError(Exception):
    """Base exception for ledger errors."""


class AccountNotFoundError(LedgerError):
    """Raised when a financial account is not found."""


class InsufficientBalanceError(LedgerError):
    """Raised when an operation exceeds available balance."""


class DuplicatePostError(LedgerError):
    """Raised when a duplicate idempotency key is posted.

    Per Section 07.1: idempotent processing.
    """


class UnbalancedEntryError(LedgerError):
    """Raised when a journal entry is unbalanced."""


class ReservationNotFoundError(LedgerError):
    """Raised when a profit reservation is not found."""


class WithdrawalNotFoundError(LedgerError):
    """Raised when a withdrawal request is not found."""


class ReconciliationNotFoundError(LedgerError):
    """Raised when a reconciliation record is not found."""


class FinancialLedger:
    """Financial ledger service per Section 07.

    Implements:
    - Financial account model (07.1)
    - Balanced double-entry journal (07.1)
    - Fill-to-ledger mapping (07.1)
    - Decimal precision with asset-specific rounding (07.1)
    - Fee accounting (07.1)
    - Realized and unrealized P&L (07.2)
    - Profit thresholds (07.3)
    - Profit reservations (07.3)
    - Reconciliation (07.4)
    - Withdrawal-request contracts (AD-007)

    All state mutations are thread-safe under a lock.
    Per Section 07.1: idempotent processing — duplicate idempotency keys
    are rejected, not double-posted.
    """

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._accounts: dict[str, FinancialAccount] = {}
        self._accounts_by_tenant_asset: dict[tuple[str, str], AccountId] = {}
        self._journal: dict[str, JournalEntry] = {}
        self._idempotency_keys: set[str] = set()
        self._fill_mappings: dict[str, FillLedgerMapping] = {}
        self._profit_thresholds: dict[str, ProfitThreshold] = {}
        self._profit_reservations: dict[str, ProfitReservationEntry] = {}
        self._withdrawals: dict[str, WithdrawalRequest] = {}
        self._reconciliations: dict[str, ReconciliationRecord] = {}
        self._realized_pnl: dict[str, Decimal] = {}  # tenant_id -> realized P&L
        self._position_cost_basis: dict[
            tuple[str, str], Decimal
        ] = {}  # (tenant_id, symbol) -> total cost basis
        self._position_quantity: dict[
            tuple[str, str], Decimal
        ] = {}  # (tenant_id, symbol) -> total quantity held

    # ── Account Management ──

    def create_account(
        self,
        *,
        tenant_id: str,
        account_type: AccountType,
        asset: str,
        initial_balance: str = "0",
    ) -> FinancialAccount:
        """Create a new financial account per Section 07.1.

        Per AD-018: durable, auditable financial records.
        """
        with self._lock:
            key = (tenant_id, asset)
            if key in self._accounts_by_tenant_asset:
                raise LedgerError(f"Account already exists for tenant {tenant_id}, asset {asset}.")
            account = FinancialAccount.create(
                tenant_id=tenant_id,
                account_type=account_type,
                asset=asset,
                initial_balance=initial_balance,
            )
            self._accounts[str(account.account_id)] = account
            self._accounts_by_tenant_asset[key] = account.account_id
            return account

    def get_account(self, account_id: AccountId | str) -> FinancialAccount:
        """Get a financial account by ID."""
        with self._lock:
            aid = str(account_id)
            account = self._accounts.get(aid)
            if account is None:
                raise AccountNotFoundError(f"Account {aid} not found.")
            return account

    def get_account_by_tenant_asset(self, tenant_id: str, asset: str) -> FinancialAccount:
        """Get a financial account by tenant and asset."""
        with self._lock:
            aid = self._accounts_by_tenant_asset.get((tenant_id, asset))
            if aid is None:
                raise AccountNotFoundError(f"No account for tenant {tenant_id}, asset {asset}.")
            return self._accounts[str(aid)]

    def get_or_create_account(
        self,
        *,
        tenant_id: str,
        asset: str,
        account_type: AccountType = AccountType.SPOT,
    ) -> FinancialAccount:
        """Get or create an account for a tenant and asset.

        Per Section 07.1: thread-safe get-or-create. The entire operation
        is performed under the lock to avoid a TOCTOU race between
        checking existence and creating the account.
        """
        with self._lock:
            return self._get_or_create_locked(tenant_id, asset, account_type)

    # ── Journal Posting ──

    def post_entry(self, entry: JournalEntry) -> JournalEntry:
        """Post a journal entry to the ledger.

        Per Section 07.1: balanced financial postings, idempotent
        processing, explicit correction entries.

        The entry is validated for balance, then each line is applied
        to the corresponding account. Debits increase asset balances,
        credits decrease them.

        Idempotency: if the entry has an idempotency_key that has
        already been posted, a DuplicatePostError is raised.
        """
        with self._lock:
            # Idempotency check
            if entry.idempotency_key is not None:
                if entry.idempotency_key in self._idempotency_keys:
                    raise DuplicatePostError(
                        f"Duplicate journal entry for idempotency key '{entry.idempotency_key}'."
                    )
                self._idempotency_keys.add(entry.idempotency_key)

            # Validate balance
            if not entry.is_balanced:
                raise UnbalancedEntryError(
                    "Cannot post unbalanced journal entry — debits must equal credits."
                )

            # Apply each line to the account
            for line in entry.lines:
                account = self._accounts.get(str(line.account_id))
                if account is None:
                    raise AccountNotFoundError(
                        f"Account {line.account_id} not found for journal entry."
                    )
                self._apply_line(account, line)

            # Mark as posted
            posted_entry = JournalEntry(
                entry_id=entry.entry_id,
                tenant_id=entry.tenant_id,
                entry_type=entry.entry_type,
                lines=entry.lines,
                reference=entry.reference,
                description=entry.description,
                idempotency_key=entry.idempotency_key,
                created_at=entry.created_at,
                posted_at=datetime.now(UTC),
            )
            self._journal[str(posted_entry.entry_id)] = posted_entry
            return posted_entry

    def _apply_line(self, account: FinancialAccount, line: JournalLine) -> None:
        """Apply a journal line to an account.

        For asset accounts: debit increases balance, credit decreases.
        """
        current = Decimal(account.balance)
        amount = Decimal(line.amount)
        if line.side is AccountSide.DEBIT:
            new_balance = current + amount
        else:
            new_balance = current - amount
            if new_balance < 0:
                raise InsufficientBalanceError(
                    f"Insufficient balance in {account.asset} account: {current} < {amount}."
                )
        updated = FinancialAccount(
            account_id=account.account_id,
            tenant_id=account.tenant_id,
            account_type=account.account_type,
            asset=account.asset,
            balance=str(quantize(new_balance, account.asset)),
            reserved_balance=account.reserved_balance,
            created_at=account.created_at,
            updated_at=datetime.now(UTC),
        )
        self._accounts[str(account.account_id)] = updated

    def get_entry(self, entry_id: JournalEntryId | str) -> JournalEntry:
        """Get a journal entry by ID."""
        with self._lock:
            eid = str(entry_id)
            entry = self._journal.get(eid)
            if entry is None:
                raise LedgerError(f"Journal entry {eid} not found.")
            return entry

    @property
    def entry_count(self) -> int:
        """Number of posted journal entries."""
        with self._lock:
            return len(self._journal)

    # ── Fill-to-Ledger Mapping ──

    def record_fill(
        self,
        *,
        tenant_id: str,
        fill: FillResult,
        symbol: str,
    ) -> FillLedgerMapping:
        """Map a fill to journal entries and record the financial effects.

        Per Section 07.1: traceable event provenance — every fill maps to
        journal entries.
        Per AD-014: exact decimal arithmetic with asset-specific precision.

        For a BUY fill:
        - Debit the base asset account (quantity acquired)
        - Credit the quote asset account (quantity * price)
        - Debit the fee asset account with the fee (separate fee entry)

        For a SELL fill:
        - Debit the quote asset account (quantity * price)
        - Credit the base asset account (quantity disposed)
        - Calculate realized P&L if cost basis is known

        Returns the FillLedgerMapping that traces the fill to its entries.
        """
        with self._lock:
            fill_id = fill.fill_id
            if fill_id in self._fill_mappings:
                return self._fill_mappings[fill_id]

            parts = symbol.split("/")
            _SYMBOL_PAIR_LEN = 2
            base_asset = parts[0] if len(parts) == _SYMBOL_PAIR_LEN else symbol
            quote_asset = parts[1] if len(parts) == _SYMBOL_PAIR_LEN else "USDT"

            qty = Decimal(fill.filled_quantity)
            price = Decimal(fill.fill_price)
            fee = Decimal(fill.fee)

            # Ensure accounts exist
            base_account = self._get_or_create_locked(tenant_id, base_asset)
            quote_account = self._get_or_create_locked(tenant_id, quote_asset)

            entry_ids: list[str] = []

            # Create and post the trade entry
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
                realized_pnl = self._calculate_realized_pnl(
                    tenant_id=tenant_id,
                    symbol=symbol,
                    qty=qty,
                    price=price,
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

            # Post the trade entry (without acquiring lock again)
            self._post_entry_locked(trade_entry)
            entry_ids.append(str(trade_entry.entry_id))

            # Record fee entry if fee > 0
            if fee > 0:
                fee_entry = self._create_fee_entry(
                    tenant_id=tenant_id,
                    quote_account=quote_account,
                    fee=fee,
                    quote_asset=quote_asset,
                    fill_id=fill_id,
                )
                self._post_entry_locked(fee_entry)
                entry_ids.append(str(fee_entry.entry_id))

            # Calculate realized P&L BEFORE updating position (uses pre-sell state)
            realized_pnl_value = self._get_realized_pnl_for_fill(
                tenant_id, symbol, fill.side, qty, price
            )

            # Update position tracking
            self._update_position(tenant_id, symbol, fill.side, qty, price)

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
            self._fill_mappings[fill_id] = mapping
            return mapping

    def _get_or_create_locked(
        self, tenant_id: str, asset: str, account_type: AccountType = AccountType.SPOT
    ) -> FinancialAccount:
        """Get or create an account while holding the lock."""
        key = (tenant_id, asset)
        aid = self._accounts_by_tenant_asset.get(key)
        if aid is not None:
            return self._accounts[str(aid)]
        account = FinancialAccount.create(
            tenant_id=tenant_id,
            account_type=account_type,
            asset=asset,
        )
        self._accounts[str(account.account_id)] = account
        self._accounts_by_tenant_asset[key] = account.account_id
        return account

    def _create_trade_entry_buy(  # noqa: PLR0913
        self,
        *,
        tenant_id: str,
        base_account: FinancialAccount,
        quote_account: FinancialAccount,
        qty: Decimal,
        price: Decimal,
        base_asset: str,
        quote_asset: str,
        fill_id: str,
    ) -> JournalEntry:
        """Create a balanced buy trade entry."""
        cost_value = quantize(qty * price, quote_asset)
        base_qty = quantize(qty, base_asset)
        return JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id=tenant_id,
            entry_type=JournalEntryType.TRADE_EXECUTION,
            lines=[
                JournalLine(
                    account_id=base_account.account_id,
                    side=AccountSide.DEBIT,
                    amount=str(base_qty),
                    asset=base_asset,
                    value=str(cost_value),
                ),
                JournalLine(
                    account_id=quote_account.account_id,
                    side=AccountSide.CREDIT,
                    amount=str(cost_value),
                    asset=quote_asset,
                    value=str(cost_value),
                ),
            ],
            reference=fill_id,
            description=f"Buy {base_qty} {base_asset} @ {price} {quote_asset}",
            idempotency_key=f"fill-{fill_id}-trade",
        )

    def _create_trade_entry_sell(  # noqa: PLR0913
        self,
        *,
        tenant_id: str,
        base_account: FinancialAccount,
        quote_account: FinancialAccount,
        qty: Decimal,
        price: Decimal,
        base_asset: str,
        quote_asset: str,
        fill_id: str,
        realized_pnl: Decimal,
    ) -> JournalEntry:
        """Create a balanced sell trade entry."""
        proceeds = quantize(qty * price, quote_asset)
        base_qty = quantize(qty, base_asset)
        return JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id=tenant_id,
            entry_type=JournalEntryType.TRADE_EXECUTION,
            lines=[
                JournalLine(
                    account_id=quote_account.account_id,
                    side=AccountSide.DEBIT,
                    amount=str(proceeds),
                    asset=quote_asset,
                    value=str(proceeds),
                ),
                JournalLine(
                    account_id=base_account.account_id,
                    side=AccountSide.CREDIT,
                    amount=str(base_qty),
                    asset=base_asset,
                    value=str(proceeds),
                ),
            ],
            reference=fill_id,
            description=f"Sell {base_qty} {base_asset} @ {price} {quote_asset}",
            idempotency_key=f"fill-{fill_id}-trade",
        )

    def _create_fee_entry(
        self,
        *,
        tenant_id: str,
        quote_account: FinancialAccount,
        fee: Decimal,
        quote_asset: str,
        fill_id: str,
    ) -> JournalEntry:
        """Create a balanced fee entry.

        Per Section 07.1: fee accounting. The fee is credited to the
        quote asset account (reducing cash) and debited to a fee expense
        account (increasing expense). This is a proper balanced
        double-entry that actually reduces the cash balance.
        """
        fee_amount = quantize(fee, quote_asset)
        # Get or create a fee expense account for this tenant
        expense_account = self._get_or_create_locked(tenant_id, f"FEE_EXPENSE_{quote_asset}")
        return JournalEntry(
            entry_id=JournalEntryId.generate(),
            tenant_id=tenant_id,
            entry_type=JournalEntryType.FEE_ACCRUAL,
            lines=[
                # Debit fee expense account (increases expense)
                JournalLine(
                    account_id=expense_account.account_id,
                    side=AccountSide.DEBIT,
                    amount=str(fee_amount),
                    asset=quote_asset,
                    value=str(fee_amount),
                ),
                # Credit quote asset account (reduces cash)
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

    def _post_entry_locked(self, entry: JournalEntry) -> JournalEntry:
        """Post an entry while already holding the lock."""
        if entry.idempotency_key is not None:
            if entry.idempotency_key in self._idempotency_keys:
                raise DuplicatePostError(
                    f"Duplicate journal entry for key '{entry.idempotency_key}'."
                )
            self._idempotency_keys.add(entry.idempotency_key)
        if not entry.is_balanced:
            raise UnbalancedEntryError("Unbalanced journal entry.")
        for line in entry.lines:
            account = self._accounts.get(str(line.account_id))
            if account is None:
                raise AccountNotFoundError(f"Account {line.account_id} not found.")
            self._apply_line(account, line)
        posted = JournalEntry(
            entry_id=entry.entry_id,
            tenant_id=entry.tenant_id,
            entry_type=entry.entry_type,
            lines=entry.lines,
            reference=entry.reference,
            description=entry.description,
            idempotency_key=entry.idempotency_key,
            created_at=entry.created_at,
            posted_at=datetime.now(UTC),
        )
        self._journal[str(posted.entry_id)] = posted
        return posted

    # ── Position Tracking & P&L ──

    def _update_position(
        self,
        tenant_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
    ) -> None:
        """Update position cost basis and quantity."""
        key = (tenant_id, symbol)
        current_qty = self._position_quantity.get(key, Decimal(0))
        current_cost = self._position_cost_basis.get(key, Decimal(0))

        if side == "buy":
            new_qty = current_qty + qty
            new_cost = current_cost + (qty * price)
            self._position_quantity[key] = new_qty
            self._position_cost_basis[key] = new_cost
        elif current_qty > 0:  # sell
            avg_cost = current_cost / current_qty if current_qty > 0 else Decimal(0)
            remaining_qty = current_qty - qty
            if remaining_qty <= 0:
                self._position_quantity[key] = Decimal(0)
                self._position_cost_basis[key] = Decimal(0)
            else:
                remaining_cost = remaining_qty * avg_cost
                self._position_quantity[key] = remaining_qty
                self._position_cost_basis[key] = remaining_cost

    def _calculate_realized_pnl(
        self,
        *,
        tenant_id: str,
        symbol: str,
        qty: Decimal,
        price: Decimal,
    ) -> Decimal:
        """Calculate realized P&L for a sell fill."""
        key = (tenant_id, symbol)
        current_qty = self._position_quantity.get(key, Decimal(0))
        current_cost = self._position_cost_basis.get(key, Decimal(0))

        if current_qty <= 0:
            return Decimal(0)

        avg_cost = current_cost / current_qty if current_qty > 0 else Decimal(0)
        sell_qty = min(qty, current_qty)
        realized = (price - avg_cost) * sell_qty
        return realized

    def _get_realized_pnl_for_fill(
        self,
        tenant_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
    ) -> Decimal:
        """Get realized P&L and update the running total."""
        if side != "sell":
            return Decimal(0)
        realized = self._calculate_realized_pnl(
            tenant_id=tenant_id,
            symbol=symbol,
            qty=qty,
            price=price,
        )
        current = self._realized_pnl.get(tenant_id, Decimal(0))
        self._realized_pnl[tenant_id] = current + realized
        return realized

    def get_realized_pnl(self, tenant_id: str) -> str:
        """Get total realized P&L for a tenant."""
        with self._lock:
            return str(self._realized_pnl.get(tenant_id, Decimal(0)))

    def get_unrealized_pnl(self, tenant_id: str, symbol: str, current_price: str) -> str:
        """Get unrealized P&L for a position at current price."""
        with self._lock:
            key = (tenant_id, symbol)
            current_qty = self._position_quantity.get(key, Decimal(0))
            current_cost = self._position_cost_basis.get(key, Decimal(0))
            if current_qty <= 0:
                return "0"
            market_value = current_qty * Decimal(current_price)
            unrealized = market_value - current_cost
            return str(quantize(unrealized, "USDT"))

    def get_pnl(
        self, tenant_id: str, *, symbol: str | None = None, current_price: str = "0"
    ) -> ProfitLoss:
        """Get P&L summary for a tenant.

        Per Section 07.2: distinguish realized net P&L from unrealized P&L.
        """
        with self._lock:
            realized = self._realized_pnl.get(tenant_id, Decimal(0))
            unrealized = Decimal(0)
            if symbol is not None and Decimal(current_price) > 0:
                key = (tenant_id, symbol)
                current_qty = self._position_quantity.get(key, Decimal(0))
                current_cost = self._position_cost_basis.get(key, Decimal(0))
                if current_qty > 0:
                    unrealized = (current_qty * Decimal(current_price)) - current_cost
            return ProfitLoss(
                tenant_id=tenant_id,
                realized_pnl=str(quantize(realized, "USDT")),
                unrealized_pnl=str(quantize(unrealized, "USDT")),
            )

    # ── Balance Queries ──

    def get_balance(self, tenant_id: str, asset: str) -> str:
        """Get the balance of an asset for a tenant.

        Per Section 07.2: available trading balance.
        """
        with self._lock:
            return self._get_balance_locked(tenant_id, asset)

    def _get_balance_locked(self, tenant_id: str, asset: str) -> str:
        """Get balance while already holding the lock.

        This is the non-locking variant used by methods that already
        acquire self._lock. Calling the public get_balance() from within
        a locked method would deadlock because threading.Lock is not
        re-entrant.
        """
        key = (tenant_id, asset)
        aid = self._accounts_by_tenant_asset.get(key)
        if aid is None:
            return "0"
        return self._accounts[str(aid)].balance

    def get_available_balance(self, tenant_id: str, asset: str) -> str:
        """Get available (unreserved) balance.

        Per Section 07.2: distinguish available trading balance from
        reserved capital.
        """
        with self._lock:
            key = (tenant_id, asset)
            aid = self._accounts_by_tenant_asset.get(key)
            if aid is None:
                return "0"
            return self._accounts[str(aid)].available_balance

    def get_reserved_balance(self, tenant_id: str, asset: str) -> str:
        """Get reserved balance for a tenant and asset."""
        with self._lock:
            key = (tenant_id, asset)
            aid = self._accounts_by_tenant_asset.get(key)
            if aid is None:
                return "0"
            return self._accounts[str(aid)].reserved_balance

    def get_withdrawable_balance(self, tenant_id: str, asset: str) -> str:
        """Get the provider-reported withdrawable balance.

        Per Section 07.2: provider-reported withdrawable balance.
        In this simulation, it equals the available balance.
        """
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
        """Add a profit threshold configuration.

        Per Section 07.3: multiple configurable thresholds for profit
        alerts, profit reservations, trading stop conditions, withdrawal-
        request preparation, financial review.
        """
        with self._lock:
            threshold = ProfitThreshold.create(
                tenant_id=tenant_id,
                threshold_type=threshold_type,
                asset=asset,
                threshold_value=threshold_value,
            )
            self._profit_thresholds[str(threshold.threshold_id)] = threshold
            return threshold

    def get_profit_thresholds(self, tenant_id: str) -> list[ProfitThreshold]:
        """Get all profit thresholds for a tenant."""
        with self._lock:
            return [t for t in self._profit_thresholds.values() if t.tenant_id == tenant_id]

    def check_thresholds(
        self, tenant_id: str, asset: str, current_pnl: str
    ) -> list[ProfitThreshold]:
        """Check if any thresholds are triggered by current P&L.

        Per Section 07.3: thresholds must not trigger duplicate financial
        effects.
        """
        with self._lock:
            triggered: list[ProfitThreshold] = []
            pnl = Decimal(current_pnl)
            for threshold in self._profit_thresholds.values():
                if not threshold.is_active:
                    continue
                if threshold.tenant_id != tenant_id:
                    continue
                if threshold.asset != asset:
                    continue
                if pnl >= Decimal(threshold.threshold_value):
                    triggered.append(threshold)
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
        """Reserve profit (lock it from available balance).

        Per Section 07.3: profit reservation is NOT a withdrawal.
        Per AD-007: profit reservations.

        This increases the account's reserved_balance and decreases the
        available balance, but does not change the total balance.
        """
        with self._lock:
            key = (tenant_id, asset)
            aid = self._accounts_by_tenant_asset.get(key)
            if aid is None:
                raise AccountNotFoundError(f"No account for tenant {tenant_id}, asset {asset}.")
            account = self._accounts[str(aid)]
            available = Decimal(account.available_balance)
            reserve_amount = Decimal(amount)
            if reserve_amount > available:
                raise InsufficientBalanceError(
                    f"Insufficient available balance to reserve: {available} < {reserve_amount}."
                )

            # Create reservation
            reservation = ProfitReservationEntry(
                reservation_id=ProfitReservationId.generate(),
                tenant_id=tenant_id,
                asset=asset,
                reserved_amount=str(quantize(reserve_amount, asset)),
                threshold_type=threshold_type,
            )
            self._profit_reservations[str(reservation.reservation_id)] = reservation

            # Update account reserved_balance
            new_reserved = Decimal(account.reserved_balance) + reserve_amount
            updated = FinancialAccount(
                account_id=account.account_id,
                tenant_id=account.tenant_id,
                account_type=account.account_type,
                asset=account.asset,
                balance=account.balance,
                reserved_balance=str(quantize(new_reserved, asset)),
                created_at=account.created_at,
                updated_at=datetime.now(UTC),
            )
            self._accounts[str(account.account_id)] = updated
            return reservation

    def release_profit_reservation(self, reservation_id: str) -> ProfitReservationEntry:
        """Release a profit reservation back to available balance.

        Per Section 07.3: released reservations return to available balance.
        """
        with self._lock:
            reservation = self._profit_reservations.get(reservation_id)
            if reservation is None:
                raise ReservationNotFoundError(f"Reservation {reservation_id} not found.")
            if not reservation.is_active:
                raise LedgerError(
                    f"Reservation {reservation_id} is not active "
                    f"(status: {reservation.status.value})."
                )

            released = reservation.release()
            self._profit_reservations[reservation_id] = released

            # Update account reserved_balance
            key = (reservation.tenant_id, reservation.asset)
            aid = self._accounts_by_tenant_asset.get(key)
            if aid is not None:
                account = self._accounts[str(aid)]
                new_reserved = Decimal(account.reserved_balance) - Decimal(
                    reservation.reserved_amount
                )
                if new_reserved < 0:
                    new_reserved = Decimal(0)
                updated = FinancialAccount(
                    account_id=account.account_id,
                    tenant_id=account.tenant_id,
                    account_type=account.account_type,
                    asset=account.asset,
                    balance=account.balance,
                    reserved_balance=str(quantize(new_reserved, account.asset)),
                    created_at=account.created_at,
                    updated_at=datetime.now(UTC),
                )
                self._accounts[str(account.account_id)] = updated
            return released

    def get_profit_reservations(self, tenant_id: str) -> list[ProfitReservationEntry]:
        """Get all profit reservations for a tenant."""
        with self._lock:
            return [r for r in self._profit_reservations.values() if r.tenant_id == tenant_id]

    def get_active_reservations(self, tenant_id: str) -> list[ProfitReservationEntry]:
        """Get active profit reservations for a tenant."""
        with self._lock:
            return [
                r
                for r in self._profit_reservations.values()
                if r.tenant_id == tenant_id and r.is_active
            ]

    # ── Withdrawal Requests ──

    def create_withdrawal_request(
        self,
        *,
        tenant_id: str,
        asset: str,
        amount: str,
        destination_address: str = "",
    ) -> WithdrawalRequest:
        """Create a withdrawal request per AD-007.

        Per Section 07.3: actual withdrawals require separate authorization
        and provider/legal eligibility.
        Per AD-029: must respect jurisdiction and provider eligibility.
        """
        with self._lock:
            # Check available balance
            key = (tenant_id, asset)
            aid = self._accounts_by_tenant_asset.get(key)
            if aid is None:
                raise AccountNotFoundError(f"No account for tenant {tenant_id}, asset {asset}.")
            account = self._accounts[str(aid)]
            available = Decimal(account.available_balance)
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
            self._withdrawals[str(request.request_id)] = request
            return request

    def get_withdrawal_request(self, request_id: str) -> WithdrawalRequest:
        """Get a withdrawal request by ID."""
        with self._lock:
            req = self._withdrawals.get(request_id)
            if req is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            return req

    def submit_withdrawal_for_approval(self, request_id: str) -> WithdrawalRequest:
        """Submit a withdrawal for approval."""
        with self._lock:
            req = self._withdrawals.get(request_id)
            if req is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            updated = req.submit_for_approval()
            self._withdrawals[request_id] = updated
            return updated

    def approve_withdrawal(self, request_id: str) -> WithdrawalRequest:
        """Approve a withdrawal (requires explicit human authorization).

        Per Section 07.3: actual withdrawals require separate authorization.
        """
        with self._lock:
            req = self._withdrawals.get(request_id)
            if req is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            approved = req.approve()
            self._withdrawals[request_id] = approved
            return approved

    def reject_withdrawal(self, request_id: str, reason: str = "") -> WithdrawalRequest:
        """Reject a withdrawal."""
        with self._lock:
            req = self._withdrawals.get(request_id)
            if req is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            rejected = req.reject(reason)
            self._withdrawals[request_id] = rejected
            return rejected

    def submit_withdrawal_to_provider(self, request_id: str) -> WithdrawalRequest:
        """Submit an approved withdrawal to the provider."""
        with self._lock:
            req = self._withdrawals.get(request_id)
            if req is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            submitted = req.submit()
            self._withdrawals[request_id] = submitted
            return submitted

    def complete_withdrawal(self, request_id: str, provider_tx_id: str = "") -> WithdrawalRequest:
        """Mark a withdrawal as completed with provider confirmation.

        Per Section 07.2: provider-reported withdrawable balance.
        """
        with self._lock:
            req = self._withdrawals.get(request_id)
            if req is None:
                raise WithdrawalNotFoundError(f"Withdrawal request {request_id} not found.")
            completed = req.complete(provider_tx_id)
            self._withdrawals[request_id] = completed

            # Deduct the withdrawn amount from the account balance
            key = (req.tenant_id, req.asset)
            aid = self._accounts_by_tenant_asset.get(key)
            if aid is not None:
                account = self._accounts[str(aid)]
                new_balance = Decimal(account.balance) - Decimal(req.amount)
                new_reserved = Decimal(account.reserved_balance)
                if new_balance < 0:
                    new_balance = Decimal(0)
                updated = FinancialAccount(
                    account_id=account.account_id,
                    tenant_id=account.tenant_id,
                    account_type=account.account_type,
                    asset=account.asset,
                    balance=str(quantize(new_balance, account.asset)),
                    reserved_balance=str(quantize(new_reserved, account.asset)),
                    created_at=account.created_at,
                    updated_at=datetime.now(UTC),
                )
                self._accounts[str(account.account_id)] = updated
            return completed

    def get_withdrawals(self, tenant_id: str) -> list[WithdrawalRequest]:
        """Get all withdrawal requests for a tenant."""
        with self._lock:
            return [w for w in self._withdrawals.values() if w.tenant_id == tenant_id]

    # ── Reconciliation ──

    def reconcile_balance(
        self,
        *,
        tenant_id: str,
        asset: str,
        exchange_balance: str,
    ) -> ReconciliationRecord:
        """Reconcile internal ledger balance with exchange-reported balance.

        Per Section 07.4: exchange-reported executions and balances must
        be reconciled with internal financial records. Discrepancies must
        produce explicit incidents or correction workflows. Silent ledger
        mutation is prohibited.
        """
        with self._lock:
            ledger_balance = self._get_balance_locked(tenant_id, asset)
            record = ReconciliationRecord(
                reconciliation_id=ReconciliationId.generate(),
                tenant_id=tenant_id,
                asset=asset,
                ledger_balance=ledger_balance,
                exchange_balance=exchange_balance,
                created_at=datetime.now(UTC),
            )
            self._reconciliations[str(record.reconciliation_id)] = record
            return record

    def resolve_reconciliation(
        self,
        reconciliation_id: str,
        notes: str = "",
    ) -> ReconciliationRecord:
        """Resolve a reconciliation discrepancy with correction notes.

        Per Section 07.4: discrepancies must produce explicit correction
        workflows. Silent ledger mutation is prohibited.
        """
        with self._lock:
            record = self._reconciliations.get(reconciliation_id)
            if record is None:
                raise ReconciliationNotFoundError(f"Reconciliation {reconciliation_id} not found.")
            if not record.has_discrepancy:
                raise LedgerError(
                    f"Reconciliation {reconciliation_id} has no discrepancy to resolve."
                )
            resolved = record.resolve(notes)
            self._reconciliations[reconciliation_id] = resolved
            return resolved

    def get_reconciliations(self, tenant_id: str) -> list[ReconciliationRecord]:
        """Get all reconciliation records for a tenant."""
        with self._lock:
            return [r for r in self._reconciliations.values() if r.tenant_id == tenant_id]

    def get_reconciliation(self, reconciliation_id: str) -> ReconciliationRecord:
        """Get a reconciliation record by ID."""
        with self._lock:
            record = self._reconciliations.get(reconciliation_id)
            if record is None:
                raise ReconciliationNotFoundError(f"Reconciliation {reconciliation_id} not found.")
            return record

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
        """Create a correction entry per Section 07.1.

        Per Section 07.1: explicit correction entries. Corrections are
        separate journal entries of type CORRECTION.
        """
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
        """Number of accounts in the ledger."""
        with self._lock:
            return len(self._accounts)

    @property
    def fill_mapping_count(self) -> int:
        """Number of fill mappings."""
        with self._lock:
            return len(self._fill_mappings)

    def reset(self) -> None:
        """Reset all ledger state (for testing only)."""
        with self._lock:
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
