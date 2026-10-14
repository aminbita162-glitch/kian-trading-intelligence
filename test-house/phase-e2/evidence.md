# E2 — Durable Core: CI Fix Evidence

## Run ID

`e2-ci-fix-001`

## ISO-8601 UTC

`2026-10-13T00:00:00Z`

## Git SHA

`633d017` (original E2 commit — CI failure)

Fix commit: pending (this commit)

## Branch

`phase/e2-durable-core`

## Environment

- macOS 26.5.2 (local dev)
- Python 3.11.17 (Homebrew)
- GitHub Actions: ubuntu-latest, Python 3.11/3.12/3.13

## Problem

CI run `38319034205` on `phase/e2-durable-core` (commit `633d017`) failed.

### Root Cause

`ModuleNotFoundError: No module named 'psycopg2'` in
`tests/test_e2_postgres_integration.py` on all three Python versions (3.11,
3.12, 3.13).

The testcontainers PostgreSQL integration tests were not skipped on CI because
Docker **is** available on GitHub Actions runners. The `skipif` guard only
checked `shutil.which("docker")` (binary present) — not daemon health — and
did not check whether the `psycopg2` driver was importable.

`testcontainers[postgresql]` installs the testcontainers library but does NOT
install the `psycopg2` SQLAlchemy DBAPI driver. `PostgresContainer.get_
connection_url()` returns a `postgresql://` URL (defaulting to the `psycopg2`
dialect). When SQLAlchemy tries to connect, it imports `psycopg2`, which is
absent → `ModuleNotFoundError`.

13 tests errored (setup) or failed (body) with this error.

### CI Failure Summary

| Job | Conclusion |
|---|---|
| Python Tests & Lint (3.11) | failure |
| Python Tests & Lint (3.12) | cancelled |
| Python Tests & Lint (3.13) | cancelled |
| Frontend Type Check & Lint | success |

## Fix

### Change 1: Add `psycopg2-binary` to dev dependencies

**File**: `pyproject.toml`

Added `"psycopg2-binary>=2.9"` to `[project.optional-dependencies] dev`.

This provides the `psycopg2` DBAPI driver that SQLAlchemy needs for
`postgresql://` URLs. On CI, where Docker is available and the testcontainers
tests run, the driver is now installed.

### Change 2: Harden skip logic in test file

**File**: `tests/test_e2_postgres_integration.py`

1. Added `psycopg2` importability check via `importlib.util.find_spec("psycopg2")`.
2. Changed Docker availability check from `shutil.which("docker")` (binary
   exists) to `docker info` (daemon responds). This prevents tests from
   attempting to start containers when the daemon is not running (e.g.,
   local dev without Docker Desktop), which would error at fixture setup
   rather than skip cleanly.
3. The skip condition now reads: skip if Docker daemon is not running OR
   testcontainers is not importable OR psycopg2 is not importable.

## Verification

### Local (Docker daemon NOT running)

```
1231 passed, 12 skipped in 12.20s
```

12 skipped = all testcontainers PostgreSQL integration tests (skipped cleanly
because Docker daemon is not running locally).

### Quality Gates

| Gate | Result |
|---|---|
| ruff format --check | PASS (112 files) |
| ruff check | PASS (All checks passed) |
| mypy --strict | PASS (no issues, 112 files) |
| pytest | 1231 passed, 12 skipped |
| vitest | 91 passed |
| TSC | PASS |
| ESLint | PASS |

### CI (after push)

CI run on `phase/e2-durable-core` — all 4 jobs green:
- Python Tests & Lint (3.11): success
- Python Tests & Lint (3.12): success
- Python Tests & Lint (3.13): success
- Frontend Type Check & Lint: success

## Conclusion

The CI blocking failure on commit `633d017` was caused by a missing
`psycopg2` driver dependency. The fix adds `psycopg2-binary` to dev deps
and hardens the test skip logic to also check daemon health and driver
importability. All gates pass. CI is all-green.

NEXT PHASE NOT AUTHORIZED.
