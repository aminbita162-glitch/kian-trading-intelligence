# F-SEC-02 / F-SEC-03 Remediation Evidence

| Field | Value |
|---|---|
| Run ID | f-sec-02-03-verify-001 |
| Date (UTC) | 2026-10-11T22:12:35Z |
| Git SHA | f3ece9ec219677e56fd4b43a5ed96f4311057bf2 |
| Branch | fix/f-sec-02-03-encryption-identity |
| Remote | origin (github.com/aminbita162-glitch/kian-trading-intelligence) |
| Repo visibility | PUBLIC (preserved per owner decision, Addendum A14) |
| Environment | macOS 26.5.2, Python 3.11.15, venv .venv |
| Tested components | services/identity/encryption.py, services/identity/persistence.py, services/identity/credential_vault.py, services/identity/database.py, services/identity/auth.py |

## F-SEC-02: AES-256-GCM Envelope Encryption

### Finding

Credential vault used a reversible XOR cipher (no authentication, no key
versioning, no tenant binding). Replaced with AES-256-GCM envelope encryption.

### Evidence

| # | Test | Command | Expected | Observed | Result |
|---|---|---|---|---|---|
| 1 | ruff format | `ruff format --check services/ packages/ tests/` | exit 0 | 96 files already formatted | PASS |
| 2 | ruff check | `ruff check services/ packages/ tests/` | exit 0 | All checks passed | PASS |
| 3 | mypy | `mypy services/ packages/ tests/` | exit 0 | no issues in 96 source files | PASS |
| 4 | pytest (full) | `pytest -v` | 1121 passed | 1121 passed in 5.41s | PASS |
| 5 | pytest (F-SEC-02) | `pytest tests/test_f_sec_02_encryption.py -v` | 22 passed | 22 passed in 0.23s | PASS |
| 6 | AES-256-GCM roundtrip | `python3 -c '...'` | encrypt→decrypt matches | plaintext matches | PASS |
| 7 | AAD mismatch fails | (covered by test_aad_mismatch_fails) | DecryptionError | DecryptionError | PASS |
| 8 | Tamper detection | (covered by test_tamper_detection) | DecryptionError | DecryptionError | PASS |
| 9 | Key versioning | (covered by test_key_version_in_envelope) | envelope records kv | kv field present | PASS |
| 10 | Fail-closed prod (missing key) | `KTI_ENVIRONMENT=production KTI_VAULT_KEY= _load_master_material()` | EncryptionConfigurationError | EncryptionConfigurationError | PASS |
| 11 | Fail-closed prod (short key) | `KTI_ENVIRONMENT=production KTI_VAULT_KEY=short _load_master_material()` | EncryptionConfigurationError | EncryptionConfigurationError | PASS |
| 12 | Fail-closed prod (valid key) | `KTI_ENVIRONMENT=production KTI_VAULT_KEY=$(python3 -c 'print("a"*32)')` | material loaded | 32 bytes loaded | PASS |
| 13 | Legacy XOR migration | `migrate_legacy_xor(legacy_hex, ...)` | envelope v1, decrypts | decrypts to original plaintext | PASS |

### Key Properties Verified

- Authenticated encryption (AES-256-GCM, 96-bit nonce, 128-bit auth tag)
- Versioned JSON envelope (v=1) with key_id, key_version, nonce, ciphertext
- Tenant/context binding via Additional Authenticated Data (AAD)
- Key versioning and rotation via HKDF-SHA256 per-version key derivation
- Fail-closed in production (KTI_VAULT_KEY must be ≥32 bytes)
- Legacy XOR migration via migrate_legacy_xor / migrate_all_legacy
- No hardcoded or logged key material
- Tamper detection (GCM auth tag verification)

## F-SEC-03: SQLAlchemy Persistent Identity Store

### Finding

Identity store was in-memory only (data lost on process restart). Replaced
with SQLAlchemy-backed persistent store with PostgreSQL (prod) / SQLite (dev).

### Evidence

| # | Test | Command | Expected | Observed | Result |
|---|---|---|---|---|---|
| 1 | pytest (F-SEC-03) | `pytest tests/test_f_sec_03_persistence.py -v` | 28 passed | 28 passed in 0.30s | PASS |
| 2 | Data survives recreation | (covered by test_data_survives_store_recreation) | data persists | data persists | PASS |
| 3 | User persisted | (covered by test_user_persisted_across_recreation) | user survives | user survives | PASS |
| 4 | Session persisted | (covered by test_session_persisted_across_recreation) | session survives | session survives | PASS |
| 5 | Tenant isolation | (covered by test_cross_tenant_*_blocked) | cross-tenant blocked | cross-tenant blocked | PASS |
| 6 | Password hashing | (covered by test_password_hashed_not_plaintext) | PBKDF2 hash | PBKDF2 hash, not plaintext | PASS |
| 7 | Schema migrations | (covered by test_schema_*_recorded) | schema_version recorded | schema_version recorded | PASS |
| 8 | Migrations idempotent | (covered by test_migrations_idempotent) | idempotent | idempotent | PASS |
| 9 | Fail-closed prod (missing URL) | `KTI_ENVIRONMENT=production KTI_DATABASE_URL= _resolve_db_url()` | PersistenceConfigurationError | PersistenceConfigurationError | PASS |
| 10 | Fail-closed prod (non-postgres) | `KTI_ENVIRONMENT=production KTI_DATABASE_URL=sqlite:///test.db` | PersistenceConfigurationError | PersistenceConfigurationError | PASS |
| 11 | Fail-closed prod (valid postgres) | `KTI_ENVIRONMENT=production KTI_DATABASE_URL=postgresql://...` | resolved | resolved to postgresql URL | PASS |
| 12 | Concurrency | (covered by test_concurrent_create_users) | thread-safe | thread-safe | PASS |
| 13 | End-to-end | (covered by test_register_authenticate_verify) | full flow works | full flow works | PASS |

### Key Properties Verified

- PersistentIdentityStore extends IdentityStore with DB persistence
- SQLite (dev) / PostgreSQL (prod) via KTI_DATABASE_URL
- Fail-closed in production (PostgreSQL URL required, non-postgreSQL rejected)
- Versioned schema migrations (schema_version table, idempotent)
- Persistent password hash storage (set/get_password_hash)
- In-memory object cache for same-reference semantics
- Thread-safe with separate persistence lock
- Data survives store recreation (verified with file-based SQLite)

## Quality Gates Summary

| Gate | Command | Result |
|---|---|---|
| ruff format | `ruff format --check services/ packages/ tests/` | PASS (96 files) |
| ruff check | `ruff check services/ packages/ tests/` | PASS (all checks passed) |
| mypy | `mypy services/ packages/ tests/` | PASS (0 issues, 96 files) |
| pytest | `pytest -v` | PASS (1121/1121) |
| TSC | `npx tsc --noEmit` | PASS (exit 0) |
| ESLint | `npm run lint` | PASS (0 errors, 7 warnings) |
| Vitest | `npm test -- --run` | PASS (91/91) |
| Secret scan | `pytest tests/test_secret_scan.py -v` | PASS (2/2) |

## CI Status

CI not triggered — branch is `fix/f-sec-02-03-encryption-identity` (fix/*
prefix). Per `.github/workflows/ci.yml`, CI only triggers on `main` and
`phase/*` branches. This is expected behavior, not a failure.

## Remote Sync

- Local SHA:  f3ece9ec219677e56fd4b43a5ed96f4311057bf2
- Remote SHA: f3ece9ec219677e56fd4b43a5ed96f4311057bf2
- Status: IN SYNC

## Conclusion

F-SEC-02 and F-SEC-03 are fully resolved. All quality gates pass. No
remaining issues. Awaiting owner approval before merge to main.
