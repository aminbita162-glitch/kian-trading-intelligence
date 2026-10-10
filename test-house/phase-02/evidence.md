# Test House — Phase 02 Evidence

## Identity and Multi-Tenant Security

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

## Test Coverage Summary

### Adversarial Access-Control Tests (Mandatory Acceptance)

| Test Module | Tests | Coverage |
|-------------|-------|----------|
| test_auth.py | 10 | Authentication, lockout, inactive accounts, cross-tenant, device registration |
| test_tenant_isolation.py | 9 | Tenant CRUD, cross-tenant rejection, user isolation, inactivity |
| test_authorization.py | 16 | RBAC, privilege escalation, step-up enforcement, session validation |
| test_mfa.py | 15 | TOTP generation/verification, MFA enable/disable, step-up grant, method mismatch |
| test_session.py | 13 | Session create/validate/revoke, expiry, step-up lifecycle, device binding |
| test_credential_vault.py | 11 | Store/retrieve, encryption verification, cross-tenant rejection, rotation, revocation |
| test_audit.py | 8 | Event creation, tenant scoping, unique IDs, timestamps, metadata, limit |
| test_identity_api.py | 11 | API endpoints: tenants, login, session validation, MFA, OpenAPI schema |
| test_secret_scan.py | 2 | No secrets in repo, no .env files committed |

### Identity API Endpoints

- `POST /tenants` — Create a new tenant
- `GET /tenants/{tenant_id}` — Get tenant by ID
- `POST /auth/login` — Authenticate user, create session
- `POST /auth/mfa/setup` — Set up MFA for a user
- `POST /auth/mfa/verify` — Verify MFA code, grant step-up
- `POST /sessions/validate` — Validate session status

### Frontend Contracts Added (Phase 02)

- UserRole, MFAMethod, SessionStatus, DeviceStatus, CredentialType
- AuditEventType (25 event types)
- ROLE_PRIVILEGE_LEVEL and canManageRole function
- Tenant, User, AuthSession, LoginRequest/LoginResponse interfaces

### Architecture Decisions Covered

- AD-002: Multi-Tenant Foundation (tenant isolation)
- AD-008: User Onboarding (user models, profiles)
- AD-010: Zero-Trust Security (RBAC, least privilege, device controls)
- AD-019: Non-Custodial Credential Vault (encrypted storage, rotation, revocation)
- AD-022: Observability and Audit (tamper-evident audit events)
- AD-026: Centralized Identity and Step-Up Authorization

### Security Findings

- F-SEC-01: Repository is PUBLIC (should be PRIVATE per Addendum A14) — flagged to owner, preserved per owner decision
- F-SEC-02: Credential vault uses simulated XOR encryption (Phase 02 dev only) — production must use managed KMS per AD-019
- F-SEC-03: Password store uses in-memory dict (Phase 02 dev only) — production must use PostgreSQL per AD-031
