# Test House — Evidence Index

| Run ID | Phase | Date (UTC) | Commit SHA | Branch | Component | Command | Expected | Observed | Status |
|--------|-------|------------|------------|--------|-----------|---------|----------|----------|--------|
| PH01-001 | 01 | 2025-10-10 | (pre-fix) acecfe9 | main | Python format/lint/tests | `ruff format --check services/ packages/ tests/` | 0 errors | 0 errors | PASS |
| PH01-002 | 01 | 2025-10-10 | (pre-fix) acecfe9 | main | Python format/lint/tests | `ruff check services/ packages/ tests/` | 0 errors | 0 errors | PASS |
| PH01-003 | 01 | 2025-10-10 | (pre-fix) acecfe9 | main | Python unit tests | `pytest -v` | 36 pass, 0 fail | 36 passed | PASS |
| PH01-004 | 01 | 2025-10-10 | (pre-fix) acecfe9 | main | mypy strict type check | `mypy services/ packages/ tests/` | 0 errors | 1 error: bare `dict` return in app.py:87 | FAIL |
| PH01-005 | 01 | 2025-10-10 | (pre-fix) acecfe9 | main | Frontend type check | `npx tsc --noEmit` | 0 errors | 0 errors | PASS |
| PH01-006 | 01 | 2025-10-10 | (pre-fix) acecfe9 | main | Frontend lint | `npm run lint` | 0 errors | 0 errors | PASS |
| PH01-007 | 01 | 2025-10-10 | (pre-fix) acecfe9 | main | Frontend tests | `npm test -- --run` | 14 pass, 0 fail | 14 passed (1 act() warning) | PASS |
| PH01-008 | 01 | 2025-10-10 | (pre-fix) acecfe9 | main | Secret scan | `pytest tests/test_secret_scan.py -v` | 0 findings | 0 findings | PASS |
| PH01-009 | 01 | 2025-10-10 | (post-fix) | fix/phase-01-audit-findings | Python format/lint/tests | `ruff format --check services/ packages/ tests/` | 0 errors | 0 errors | PASS |
| PH01-010 | 01 | 2025-10-10 | (post-fix) | fix/phase-01-audit-findings | Python format/lint/tests | `ruff check services/ packages/ tests/` | 0 errors | 0 errors | PASS |
| PH01-011 | 01 | 2025-10-10 | (post-fix) | fix/phase-01-audit-findings | Python unit tests | `pytest -v` | 36 pass, 0 fail | 36 passed | PASS |
| PH01-012 | 01 | 2026-10-10 | (post-fix) | fix/phase-01-audit-findings | mypy strict type check | `mypy services/ packages/ tests/` | 0 errors | 0 errors | PASS |
| PH01-013 | 01 | 2025-10-10 | (post-fix) | fix/phase-01-audit-findings | Frontend type check | `npx tsc --noEmit` | 0 errors | 0 errors | PASS |
| PH01-014 | 01 | 2025-10-10 | (post-fix) | fix/phase-01-audit-findings | Frontend lint | `npm run lint` | 0 errors | 0 errors | PASS |
| PH01-015 | 01 | 2025-10-10 | (post-fix) | fix/phase-01-audit-findings | Frontend tests | `npm test -- --run` | 14 pass, 0 fail, 0 warnings | 14 passed, 0 warnings | PASS |
| PH01-016 | 01 | 2025-10-10 | (post-fix) | fix/phase-01-audit-findings | Secret scan | `pytest tests/test_secret_scan.py -v` | 0 findings | 0 findings | PASS |

## Audit Findings (Phase 01)

| ID | Finding | Resolution |
|----|---------|------------|
| F-01 | mypy --strict fails: bare `dict` return type in `services/core/app.py:87` | Fixed: `dict` → `dict[str, str]` |
| F-02 | `docs/architecture.md` and `CHANGELOG.md` state "Python 3.12+" but pyproject.toml requires >=3.11 | Fixed: corrected to "Python 3.11+" |
| F-03 | Repository is PUBLIC (should be PRIVATE per Addendum A14) | Owner decision — visibility preserved per owner instruction |
| F-04 | `test-house/index.md` empty — no Phase 01 evidence records | Fixed: populated with actual run results |
| F-05 | CI workflow does not run `mypy` type checking | Fixed: added mypy step to `ci.yml` |
| F-06 | Frontend `App.test.tsx` produces React `act()` warning | Fixed: wrapped state update in `act()` / `waitFor` |

## Phase 02 — Identity and Multi-Tenant Security

| Run ID | Phase | Date (UTC) | Commit SHA | Branch | Component | Command | Expected | Observed | Status |
|--------|-------|------------|------------|--------|-----------|---------|----------|----------|--------|
| PH02-001 | 02 | 2026-10-10 | (pre-commit) 90ba841 | phase/02-identity-security | Python format check | `ruff format --check services/ packages/ tests/` | 0 errors | 0 errors | PASS |
| PH02-002 | 02 | 2026-10-10 | (pre-commit) 90ba841 | phase/02-identity-security | Python lint | `ruff check services/ packages/ tests/` | 0 errors | 0 errors | PASS |
| PH02-003 | 02 | 2026-10-10 | (pre-commit) 90ba841 | phase/02-identity-security | mypy strict type check | `mypy services/ packages/ tests/` | 0 errors | 0 errors | PASS |
| PH02-004 | 02 | 2026-10-10 | (pre-commit) 90ba841 | phase/02-identity-security | Python unit tests | `pytest -v` | 127 pass, 0 fail | 127 passed | PASS |
| PH02-005 | 02 | 2026-10-10 | (pre-commit) 90ba841 | phase/02-identity-security | Secret scan | `pytest tests/test_secret_scan.py -v` | 0 findings | 0 findings | PASS |
| PH02-006 | 02 | 2026-10-10 | (pre-commit) 90ba841 | phase/02-identity-security | Frontend type check | `npx tsc --noEmit` | 0 errors | 0 errors | PASS |
| PH02-007 | 02 | 2026-10-10 | (pre-commit) 90ba841 | phase/02-identity-security | Frontend lint | `npm run lint` | 0 errors | 0 errors | PASS |
| PH02-008 | 02 | 2026-10-10 | (pre-commit) 90ba841 | phase/02-identity-security | Frontend tests | `npm test -- --run` | 29 pass, 0 fail | 29 passed | PASS |

## Phase 03 — Market Data Foundation

| Run ID | Phase | Date (UTC) | Commit SHA | Branch | Component | Command | Expected | Observed | Status |
|--------|-------|------------|------------|--------|-----------|---------|----------|----------|--------|
| PH03-001 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Python format check | `ruff format --check services/ packages/ tests/` | 0 errors | 0 errors (44 files clean) | PASS |
| PH03-002 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Python lint | `ruff check services/ packages/ tests/` | 0 errors | All checks passed | PASS |
| PH03-003 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | mypy strict type check | `mypy services/ packages/ tests/` | 0 errors | Success: no issues found in 44 source files | PASS |
| PH03-004 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Python unit tests | `pytest -v` | 245 pass, 0 fail | 245 passed in 4.08s | PASS |
| PH03-005 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Secret scan | `pytest tests/test_secret_scan.py -v` | 0 findings | 2 passed (0 findings) | PASS |
| PH03-006 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Frontend type check | `npx tsc --noEmit` | 0 errors | 0 errors | PASS |
| PH03-007 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Frontend lint | `npm run lint` | 0 errors | 0 errors | PASS |
| PH03-008 | 03 | 2026-10-10 | (pre-commit) 8967988 | phase/03-market-data | Frontend tests | `npm test -- --run` | 29 pass, 0 fail | 29 passed (3 test files) | PASS |

## Phase 09 — Security, Resilience, and Scale

| Run ID | Phase | Date (UTC) | Commit SHA | Branch | Component | Command | Expected | Observed | Status |
|--------|-------|------------|------------|--------|-----------|---------|----------|----------|--------|
| PH09-001 | 09 | 2026-10-10 | (pre-commit) 5710611 | phase/09-security-resilience-scale | Python format check | `ruff format --check services/ packages/ tests/` | 0 errors | 88 files already formatted | PASS |
| PH09-002 | 09 | 2026-10-10 | (pre-commit) 5710611 | phase/09-security-resilience-scale | Python lint | `ruff check services/ packages/ tests/` | 0 errors | All checks passed | PASS |
| PH09-003 | 09 | 2026-10-10 | (pre-commit) 5710611 | phase/09-security-resilience-scale | mypy strict type check | `mypy services/ packages/ tests/` | 0 errors | Success: no issues found in 88 source files | PASS |
| PH09-004 | 09 | 2026-10-10 | (pre-commit) 5710611 | phase/09-security-resilience-scale | Python unit tests | `pytest -v` | 933 pass, 0 fail | 933 passed in 4.42s | PASS |
| PH09-005 | 09 | 2026-10-10 | (pre-commit) 5710611 | phase/09-security-resilience-scale | Secret scan | `pytest tests/test_secret_scan.py -v` | 0 findings | 2 passed (0 findings) | PASS |
| PH09-006 | 09 | 2026-10-10 | (pre-commit) 5710611 | phase/09-security-resilience-scale | Frontend type check | `npx tsc --noEmit` | 0 errors | 0 errors | PASS |
| PH09-007 | 09 | 2026-10-10 | (pre-commit) 5710611 | phase/09-security-resilience-scale | Frontend lint | `npm run lint` | 0 errors | 0 errors (7 react-refresh warnings) | PASS |
| PH09-008 | 09 | 2026-10-10 | (pre-commit) 5710611 | phase/09-security-resilience-scale | Frontend tests | `npm test -- --run` | 91 pass, 0 fail | 91 passed (7 test files) | PASS |
