# E4 — Safety Plane Hardening — Evidence Record

**Run ID:** 38384898833
**ISO-8601 UTC:** 2026-10-13T10:42:00Z
**Git SHA:** 206b68945a34e46ba33ab30dc2d5a178e63a7ff5
**Branch:** phase/e4-safety-plane-hardening
**Environment:** macOS 26.5.2, Python 3.11.15, Node.js 24
**Commit message:** feat(e4): safety plane hardening — signed risk tokens, policy-as-code, trust-domain separation, formal models, Hypothesis stateful tests

## Deliverables

E4 (Safety Plane Hardening) delivers:

1. **Signed risk authorization tokens** (`packages/contracts/risk_token.py`)
   — HMAC-SHA256 signed tokens with tamper, expiry, and replay detection.
   Trust-domain separated: signing key from `KTI_RISK_TOKEN_KEY`, distinct
   from vault key `KTI_VAULT_KEY`.

2. **Policy-as-code** (`packages/contracts/policy_as_code.py`)
   — Declarative risk policy rules (`PolicyAsCodeRule`, `PolicyAsCodePolicy`)
   with standard rules (emergency stop, session state, exposure limit, daily
   loss, drawdown, concentration). Fail-closed by default.

3. **Trust-domain separation** (`packages/contracts/trust_domains.py`)
   — Verifiable separation of kernel and vault trust domains. Different env
   vars, no cross-read, distinct derived keys.

4. **Formal models** (`formal/`)
   — TLA+ specifications for OrderModel, SessionModel, ReservationModel,
   SafeHaltModel. Python checker (`formal/formal_checker.py`) validates
   implementation invariants against the formal models.

5. **Hypothesis stateful tests** (`tests/test_e4_hypothesis_stateful.py`)
   — RuleBasedStateMachine exploring the risk kernel state space with
   invariants checked at every step. Property-based tests for determinism,
   emergency stop, and sell-during-emergency-stop.

## Quality Gates

| Gate | Command | Expected | Observed | Result |
|------|---------|----------|----------|--------|
| Ruff format | `ruff format services/ packages/ tests/ formal/` | 0 errors | 130 files unchanged | PASS |
| Ruff check | `ruff check services/ packages/ tests/ formal/` | 0 errors | All checks passed | PASS |
| Mypy | `mypy services/ packages/ tests/ formal/` | 0 errors | no issues found in 129 source files | PASS |
| Import-linter | `lint-imports` | 3/3 KEPT | 3 kept, 0 broken | PASS |
| Pytest | `pytest -x -q` | all pass | 1339 passed, 12 skipped | PASS |
| Coverage | `pytest --cov --cov-fail-under=80` | ≥80% | 89.10% | PASS |
| Secret scan | `pytest tests/test_secret_scan.py -v` | 0 findings | 2 passed | PASS |
| TSC | `npx tsc --noEmit` | 0 errors | clean | PASS |
| ESLint | `npm run lint` | 0 errors | 0 errors (7 warnings) | PASS |
| Vitest | `npm test -- --run` | all pass | 91 passed | PASS |

## CI Status

| Job | Status | Conclusion |
|-----|--------|------------|
| Python Tests & Lint (3.11) | completed | success |
| Python Tests & Lint (3.12) | completed | success |
| Python Tests & Lint (3.13) | completed | success |
| Frontend Type Check & Lint | completed | success |

**CI Run ID:** 38384898833
**CI URL:** https://github.com/aminbita162-glitch/kian-trading-intelligence/actions/runs/38384898833
**All 4 jobs green:** YES

## Remote Verification

- **Remote SHA:** `git rev-parse origin/phase/e4-safety-plane-hardening` = `206b68945a34e46ba33ab30dc2d5a178e63a7ff5`
- **HEAD SHA:** `git rev-parse HEAD` = `206b68945a34e46ba33ab30dc2d5a178e63a7ff5`
- **SHA match:** YES

## Files Changed (17 files, +2616 lines)

### New contracts (packages/contracts/)
- `policy_as_code.py` — Declarative risk policy rules and standard policy factory
- `risk_token.py` — HMAC-SHA256 signed risk authorization tokens with tamper/expiry/replay detection
- `trust_domains.py` — Trust-domain separation verification (kernel vs vault)

### New formal models (formal/)
- `__init__.py` — Package init
- `formal_checker.py` — Python checker validating implementation invariants
- `OrderModel.tla` — TLA+ formal model of order state machine
- `SessionModel.tla` — TLA+ formal model of session state machine
- `ReservationModel.tla` — TLA+ formal model of reservation lifecycle
- `SafeHaltModel.tla` — TLA+ formal model of SAFE_HALT protocol
- `README.md` — Formal models documentation

### New tests (tests/)
- `test_e4_formal_models.py` — Formal model invariant tests (15 tests)
- `test_e4_hypothesis_stateful.py` — Hypothesis stateful + property-based tests
- `test_e4_policy_as_code.py` — Policy-as-code rule evaluation tests
- `test_e4_risk_tokens.py` — Signed risk token tamper/expiry/replay/malformed/AAD tests
- `test_e4_trust_domains.py` — Trust-domain separation verification tests

### Modified
- `.importlinter` — Added `formal` to root_packages, added formal-is-not-imported-by-contracts contract
- `pyproject.toml` — Added `hypothesis>=6.100` to dev deps, registered `formal` package

## Fixes Applied During E4

- mypy `no-untyped-call` on `run_state_machine_as_test` — added `# type: ignore[no-untyped-call]`
  (Hypothesis's stateful test runner is untyped).

## Repository Visibility

PUBLIC (preserved per owner decision, Addendum A14).

## NEXT PHASE NOT AUTHORIZED
