# Phase E3 — Structure and Verification Separation

## Evidence Record

| Field | Value |
|-------|-------|
| Run ID | e3-rls-fix-20261013 |
| Timestamp (UTC) | 2026-10-13T00:31:45Z |
| Git SHA | b947ba413c195e24148a15abcd6199be3a0486bb |
| Branch | phase/e3-structure-verification-separation |
| Remote | origin (github.com/aminbita162-glitch/kian-trading-intelligence) |
| Remote SHA | b947ba413c195e24148a15abcd6199be3a0486bb |
| CI Run ID | 38327506431 |
| CI Status | completed / success (4/4 jobs green) |
| Environment | macOS 26.5.2, Python 3.11 (venv), Node.js (apps/web) |

## Phase Scope

Split monolithic `services/core/app.py` into domain routers, move
simulators/fault injectors/readiness generators/test harnesses to
`simulation/` package (outside deployable `services/` tree),
`ExchangeAdapter` Protocol in `packages/contracts/exchange_adapter.py`,
import-linter layer contracts, Decimal-only lint on financial modules,
coverage 80% threshold.

## RLS Fix (this commit)

**Problem:** PostgreSQL CI failed because RLS policies referenced
`tenant_id` on tables that do not have that column:
`ledger_journal_lines`, `ledger_idempotency_keys`,
`ledger_fill_mappings`. These tables are linked to parent rows via
`entry_id` / `idempotency_key` / `fill_id` — they do not have
`tenant_id`.

**Fix:** Removed the three tables from both `_apply_rls_policies`
and `_revert_rls_policies` table lists in
`services/ledger/persistence.py`.

**Verification:** Cross-checked every table in the ORM against the
RLS table list — all 10 remaining RLS tables have `tenant_id`; no
table without `tenant_id` is included.

## Commit History (E3 branch)

1. `73a37d9` — feat(e3): structure-verification separation — split
   app.py into routers, move simulators to simulation/ package,
   ExchangeAdapter Protocol, import-linter contracts, Decimal-only
   lint, coverage 80% threshold
2. `3f31cca` — fix(e3): CREATE POLICY IF NOT EXISTS not valid
   PostgreSQL — use DROP IF EXISTS + CREATE
3. `b947ba4` — fix(e3): remove tables without tenant_id from RLS
   policy lists

## Local Gates

| Gate | Command | Result |
|------|---------|--------|
| ruff format | `ruff format --check services/ packages/ tests/` | PASS — 119 files already formatted |
| ruff check | `ruff check services/ packages/ tests/` | PASS — All checks passed |
| mypy | `mypy services/ packages/ tests/` | PASS — no issues found in 119 source files |
| import-linter | `lint-imports` | PASS — 2/2 KEPT (contracts=leaf, services↛simulation) |
| pytest | `pytest -v` | PASS — 1269 passed, 12 skipped |
| coverage | `pytest --cov=services --cov=packages --cov=simulation --cov-fail-under=80` | PASS — 88.87% (≥80% required) |
| secret scan | `pytest tests/test_secret_scan.py -v` | PASS — 2/2 passed |
| TSC | `npx tsc --noEmit` (apps/web) | PASS — clean |
| ESLint | `npm run lint` (apps/web) | PASS — 0 errors (7 warnings: react-refresh) |
| vitest | `npm test -- --run` (apps/web) | PASS — 91/91 passed |

## CI Gates (GitHub Actions, run 38327506431)

| Job | Duration | Result |
|-----|----------|--------|
| Python Tests & Lint (3.13) | 1m11s | success |
| Frontend Type Check & Lint | 18s | success |
| Python Tests & Lint (3.11) | 1m37s | success |
| Python Tests & Lint (3.12) | 1m54s | success |

**CI conclusion:** success (4/4 jobs green)

## Acceptance Criteria

- [x] Production `services/` tree contains no simulators, fault
      injectors, readiness generators, or test harnesses
- [x] `ExchangeAdapter` Protocol in `packages/contracts/` — execution
      engine depends on protocol, not concrete simulator
- [x] Monolithic `services/core/app.py` split into domain routers
      (`services/core/routers/{health,identity,market_data,client,release}.py`)
- [x] Import-linter layer contracts enforced (2/2 KEPT)
- [x] Decimal-only lint on financial modules (AST-based, no float())
- [x] Coverage 80% threshold enforced (88.87% actual)
- [x] CI all-green on Python 3.11/3.12/3.13 + Frontend

## Status

**E3 COMPLETE** — all local and CI gates pass. Awaiting owner approval
before merge to main.

NEXT PHASE NOT AUTHORIZED.
