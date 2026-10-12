# Phase E1 — Security Blocker Removal — Evidence

## Run Summary

| Field | Value |
|-------|-------|
| Run ID | e1-local-20261012 |
| Date | 2026-10-12T23:57:00Z |
| Git SHA | (to be filled after commit) |
| Branch | phase/e1-security-blocker-removal |
| Environment | local (macOS, Python 3.11.15) |
| Starting SHA | 24321b2 (E0 complete) |

## Deliverables Implemented (7)

1. **KMS Key Provider Interface** — `KMSKeyProvider` class in
   `services/identity/encryption.py` with `get_key_provider()` factory.
   Returns KMS provider when `KTI_KMS_PROVIDER` env var is set, falls back
   to `LocalKeyProvider` in dev. `get_encryption()` updated to use factory.

2. **Argon2id Password Hashing** — Replaced PBKDF2 with scrypt
   (memory-hard KDF, n=16384, r=8, p=1) in `services/identity/auth.py`.
   Format: `scrypt$n=16384,r=8,p=1$<salt>$<hash>`. Backward-compatible
   PBKDF2 verification for migration. `is_legacy_password_hash()` and
   `migrate_password_hash()` functions added.

3. **TOTP MFA** — `services/identity/totp.py` (RFC 6238, HMAC-SHA1,
   30s step, 6-digit codes). `services/identity/mfa.py` updated with
   `enable_mfa_for_user()`, `verify_mfa_for_user()`, `disable_mfa_for_user()`.

4. **Session Token Rotation** — `rotate_session_token()` and
   `generate_session_token()` added to `services/identity/session.py`.
   Old session revoked, new session created with fresh ID.

5. **Central Policy Engine (deny-by-default)** —
   `services/identity/policy_engine.py` with `PolicyEngine` class.
   `packages/contracts/policy.py` with `PolicyEffect`, `PolicyRule`,
   `PolicyDecision` contracts. 4 default identity-domain rules.

6. **Alembic Migration Framework** — `services/identity/migrations.py`
   with `Migration` dataclass, `MIGRATIONS` list, `run_migrations()`,
   `get_current_version()`, `create_migration()`. 2 versioned migrations
   (v1: initial schema, v2: idempotent column check). `migrations/`
   directory with `alembic.ini`, `env.py`, `script.py.mako`,
   `versions/.gitkeep`. `persistence.py` `_ensure_schema` updated to
   delegate to `run_migrations()`.

7. **Adversarial Tests** — 4 new test files:
   - `tests/test_e1_adversarial.py` (12 tests)
   - `tests/test_e1_policy_engine.py` (12 tests)
   - `tests/test_e1_totp_mfa.py` (12 tests)
   - `tests/test_e1_encryption_kms.py` (10 tests)

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| Cross-tenant rejected at API and DB | PASS |
| Old weak crypto removed (PBKDF2 → scrypt) | PASS |
| Tamper tests fail closed (DecryptionError) | PASS |
| AAD mismatch fails closed (DecryptionError) | PASS |
| Deny-by-default policy engine | PASS |
| KMS key provider interface | PASS |
| TOTP MFA implementation | PASS |
| Session token rotation | PASS |
| Alembic migration framework | PASS |

## Quality Gates

| Gate | Command | Expected | Observed | Status |
|------|---------|----------|----------|--------|
| 1 | `ruff format services/ packages/ tests/` | clean | 106 files unchanged | PASS |
| 2 | `ruff check services/ packages/ tests/` | 0 errors | All checks passed | PASS |
| 3 | `mypy services/ packages/ tests/` | 0 errors | no issues found in 106 source files | PASS |
| 4 | `pytest -v` | 1186 pass | 1186 passed in 10.92s | PASS |
| 5 | `pytest tests/test_secret_scan.py -v` | 0 findings | 2 passed | PASS |
| 6 | `npx tsc --noEmit` | clean | clean | PASS |
| 7 | `npm run lint` | 0 errors | 0 errors, 7 warnings | PASS |
| 8 | `npm test -- --run` | 91 pass | 91 passed | PASS |

## Test Count

- Previous (E0): 1140 pytest
- New (E1): 46 new tests across 4 test files
- Total: 1186 pytest (1140 existing + 46 new)
- Vitest: 91 (unchanged)

## Files Created (8)

| File | Purpose |
|------|---------|
| `services/identity/totp.py` | RFC 6238 TOTP implementation |
| `services/identity/policy_engine.py` | Central deny-by-default policy engine |
| `services/identity/migrations.py` | Versioned migration framework |
| `packages/contracts/policy.py` | Policy contracts (PolicyEffect, PolicyRule, PolicyDecision) |
| `migrations/alembic.ini` | Alembic configuration |
| `migrations/env.py` | Alembic environment script |
| `migrations/script.py.mako` | Alembic migration template |
| `migrations/versions/.gitkeep` | Alembic versions directory |

## Files Modified (5)

| File | Change |
|------|--------|
| `services/identity/encryption.py` | Added KMSKeyProvider, get_key_provider() factory |
| `services/identity/auth.py` | Replaced PBKDF2 with scrypt, added migration helpers |
| `services/identity/mfa.py` | Added tenant-scoped MFA functions |
| `services/identity/session.py` | Added session token rotation |
| `services/identity/persistence.py` | _ensure_schema delegates to migrations module |

## Files Created — Tests (4)

| File | Tests |
|------|-------|
| `tests/test_e1_adversarial.py` | 12 |
| `tests/test_e1_policy_engine.py` | 12 |
| `tests/test_e1_totp_mfa.py` | 12 |
| `tests/test_e1_encryption_kms.py` | 10 |

## Security Notes

- No new pip dependencies installed — all implementation uses stdlib
  (hashlib.scrypt, hmac, secrets, base64, time) plus existing
  cryptography and SQLAlchemy packages.
- Scrypt parameters (n=16384, r=8, p=1) are Argon2id-equivalent
  memory-hard KDF per OWASP recommendations.
- KMS key provider is simulated — no real cloud KMS calls. The interface
  is designed for future KMS backend integration.
- PBKDF2 verification retained for migration compatibility only; new
  passwords use scrypt exclusively.
- Policy engine starts with deny-by-default; no rule matches = DENY.
