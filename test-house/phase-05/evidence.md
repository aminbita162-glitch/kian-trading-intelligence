# Phase 05 — Financial Ledger and Profit Policies — Test-House Evidence

## Run ID
phase-05-financial-ledger-001

## Timestamp (ISO-8601 UTC)
2026-10-10T03:35:00Z

## Git SHA
e103517

## Branch
phase/05-financial-ledger

## Environment
- Python: 3.11.15
- Platform: macOS (darwin)
- Pytest: 9.1.1
- Ruff: 0.8.x
- Mypy: 1.13+
- Node/npm for frontend gates

## Architecture Decisions
- AD-007: realized net-profit, configurable thresholds, profit reservations, controlled withdrawal-request workflows
- AD-018: balanced journal postings, exact decimal arithmetic, idempotent accounting, configurable profit policies

## Deliverables (11/11)
1. Financial account model (Section 07.1) — `contracts.ledger.FinancialAccount`
2. Balanced double-entry journal (Section 07.1) — `contracts.ledger.JournalEntry`, `JournalLine`
3. Fill-to-ledger mapping (Section 07.1) — `contracts.ledger.FillLedgerMapping`, `services.ledger.FinancialLedger.record_fill`
4. Decimal precision with asset-specific rounding (Section 07.1) — `contracts.ledger.quantize`, `ASSET_PRECISION`
5. Fee accounting (Section 07.1) — `services.ledger.FinancialLedger._create_fee_entry`
6. Realized and unrealized P&L (Section 07.2) — `services.ledger.FinancialLedger.get_realized_pnl`, `get_unrealized_pnl`, `get_pnl`
7. Profit thresholds (Section 07.3) — `services.ledger.FinancialLedger.add_profit_threshold`, `check_thresholds`
8. Profit reservations (Section 07.3) — `services.ledger.FinancialLedger.reserve_profit`, `release_profit_reservation`
9. Reconciliation (Section 07.4) — `services.ledger.FinancialLedger.reconcile_balance`, `resolve_reconciliation`
10. Withdrawal-request contracts (AD-007) — `contracts.ledger.WithdrawalRequest`, `services.ledger.FinancialLedger.create_withdrawal_request` + lifecycle
11. Financial invariant tests (Section 07) — `tests/test_financial_ledger.py::TestFinancialInvariants`, `TestFinancialInvariantExtended`

## Deadlock Fix (re-entrant lock hazard)

### Root cause
`reconcile_balance()` acquired `self._lock` (a `threading.Lock`, which is NOT re-entrant),
then called `self.get_balance()` which re-acquired `self._lock` — a deadlock. The test
`TestReconciliation::test_matched_reconciliation` confirmed the deadlock with a
pytest-timeout signal at `services/ledger/__init__.py:700`.

### Fix
1. Added `_get_balance_locked()` — a private variant that reads state directly without
   acquiring the lock. `get_balance()` now delegates to it under the lock.
2. `reconcile_balance()` now calls `_get_balance_locked()` instead of `get_balance()`.
3. Fixed TOCTOU race in `get_or_create_account()` — the entire operation now runs under
   one lock acquisition, delegating to `_get_or_create_locked()`.
4. Audited all other locked methods: `create_account`, `get_account`, `get_account_by_tenant_asset`,
   `post_entry`, `record_fill`, `get_realized_pnl`, `get_unrealized_pnl`, `get_pnl`,
   `get_available_balance`, `get_reserved_balance`, `reserve_profit`, `release_profit_reservation`,
   `create_withdrawal_request`, `complete_withdrawal`, `reconcile_balance`,
   `resolve_reconciliation`, `create_correction_entry` — all confirmed safe (no nested lock
   acquisition).

### Regression tests added
- `TestDeadlockRegression::test_reconcile_balance_does_not_deadlock`
- `TestDeadlockRegression::test_reconcile_balance_with_discrepancy_no_deadlock`
- `TestDeadlockRegression::test_concurrent_reconcile_balance_no_deadlock` (4 threads × 20 iterations)
- `TestConcurrencyHazards::test_concurrent_record_fill_thread_safety` (4 threads × 10 fills)
- `TestConcurrencyHazards::test_concurrent_reserve_and_release` (4 threads × 10 cycles)
- `TestConcurrencyHazards::test_concurrent_get_or_create_account` (8 threads, TOCTOU regression)
- `TestFinancialInvariantExtended::test_concurrent_fills_preserve_balance_invariant`

## Evidence Records

### E-PH05-001: Python backend tests
- **Command**: `python -m pytest --timeout=30 -v`
- **Expected**: all tests pass
- **Observed**: 524 passed in 4.20s
- **Status**: PASS
- **Breakdown**: 370 existing (phases 01-04) + 154 new (phase 05: 75 contract + 79 service/invariant)

### E-PH05-002: Ruff format check
- **Command**: `ruff format --check services/ packages/ tests/`
- **Expected**: 0 files reformatted
- **Observed**: All files already formatted
- **Status**: PASS

### E-PH05-003: Ruff lint check
- **Command**: `ruff check services/ packages/ tests/`
- **Expected**: 0 errors
- **Observed**: All checks passed
- **Status**: PASS

### E-PH05-004: Mypy type check
- **Command**: `mypy services/ packages/ tests/`
- **Expected**: no issues
- **Observed**: Success: no issues found in 62 source files
- **Status**: PASS

### E-PH05-005: Frontend TypeScript check
- **Command**: `npx tsc --noEmit`
- **Expected**: exit code 0, no errors
- **Observed**: clean (no output, exit 0)
- **Status**: PASS

### E-PH05-006: Frontend ESLint check
- **Command**: `npm run lint`
- **Expected**: exit code 0, no errors
- **Observed**: clean (exit 0)
- **Status**: PASS

### E-PH05-007: Frontend vitest
- **Command**: `npm test -- --run`
- **Expected**: all tests pass
- **Observed**: 3 test files, 29 tests passed
- **Status**: PASS

### E-PH05-008: Secret scan
- **Command**: `python -m pytest tests/test_secret_scan.py -v`
- **Expected**: 2 tests pass, 0 findings
- **Observed**: 2 passed in 0.03s
- **Status**: PASS

### E-PH05-009: Deadlock regression
- **Command**: `python -m pytest tests/test_financial_ledger.py::TestDeadlockRegression -v --timeout=10`
- **Expected**: all deadlock regression tests pass without timeout
- **Observed**: 3 passed
- **Status**: PASS

### E-PH05-010: Concurrency hazard tests
- **Command**: `python -m pytest tests/test_financial_ledger.py::TestConcurrencyHazards -v --timeout=30`
- **Expected**: all concurrency tests pass without deadlock
- **Observed**: 3 passed
- **Status**: PASS

## Files
- `packages/contracts/ledger.py` — financial ledger contracts (accounts, journal, P&L, thresholds, reservations, withdrawals, reconciliation)
- `services/ledger/__init__.py` — FinancialLedger service with thread-safe methods
- `tests/test_financial_contracts.py` — 75 contract tests
- `tests/test_financial_ledger.py` — 79 service + invariant + deadlock + concurrency tests
- `test-house/phase-05/evidence.md` — this evidence record

## Security Findings
- **F-SEC-01** (from Phase 02): Repo is PUBLIC — should be PRIVATE per Addendum A14.
  Owner decided to keep it public; preserved, not changed.
