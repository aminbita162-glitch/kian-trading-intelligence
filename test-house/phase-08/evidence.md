# Phase 08 — MacBook and iPhone Applications — Evidence

## Run ID: PHASE-08-RUN-01

- **Date**: 2026-10-10T04:56:00Z (UTC)
- **Git SHA**: `23a9156` (pre-commit; SHA will update after commit)
- **Branch**: `phase/08-client-apps`
- **Environment**: macOS 26.5.2, Python 3.11.15, pytest 9.1.1, ruff, mypy --strict, Node.js, Vitest 2.1.9

## Deliverables (12/12)

1. **Tauri MacBook application** — `apps/macbook/src-tauri/`
   - `tauri.conf.json` with `frontendDist` → `../web/dist`, `devUrl` → localhost:5173
   - `Cargo.toml` with tauri v2 dependency, `crate-type = ["staticlib", "cdylib", "lib"]`
   - `src/main.rs` entry point calling `run()`, `src/lib.rs` with `tauri::Builder`
2. **Responsive iPhone PWA** — `apps/web/public/manifest.json`, `apps/web/index.html`
   - Manifest with `display: "standalone"`, icons, theme colors
   - Meta tags: `apple-mobile-web-app-capable`, `theme-color`
3. **Onboarding** — `OnboardingStep` enum (8-step wizard), `next_step()` logic
4. **Trading dashboard** — `apps/web/src/views/TradingCenter.tsx`
5. **Mining dashboard** — `apps/web/src/views/MiningCenter.tsx`
6. **Financial dashboard** — `apps/web/src/views/FinancialCenter.tsx`
7. **Calendar scheduler** — `apps/web/src/views/CalendarScheduler.tsx`
8. **Secure remote commands** — `RemoteCommandService` (AD-027)
   - Step-up auth for 5 high-risk commands (EMERGENCY_STOP, START_SESSION, STOP_SESSION, CANCEL_ORDER, UPDATE_RISK_POLICY)
   - Idempotency keys, command expiry, tenant isolation
   - VIEW_POSITIONS and VIEW_LEDGER do not require step-up
9. **Notification hub** — `NotificationService` (AD-009)
   - `NotificationCreateRequest` Pydantic model, preferences, priority levels
   - `_should_deliver` via dict lookup (PLR0911 fix)
10. **Connected-account settings** — `apps/web/src/views/ConnectedAccounts.tsx`
    - Withdrawal prohibition enforced (AD-019)
11. **Incident and recovery interface** — `IncidentService` (AD-017)
    - `IncidentCreateRequest` Pydantic model, severity levels, human approval for critical
    - Resolution tracking with timestamps
12. **End-to-end simulated workflows** — `run_simulated_workflow()`
    - Exercises all dashboard areas, sends notifications, returns workflow ID

## Architecture Decisions

- **AD-009**: Notification hub — alert preferences, priority-based delivery
- **AD-027**: Secure remote commands — step-up authentication, idempotency, expiry
- **AD-030**: Client application architecture — Tauri MacBook + responsive PWA iPhone
- **AD-031**: Technology stack — React/TypeScript frontend, Tauri native shell

## Quality Gates

### Python Gates

| Gate | Command | Result |
|------|---------|--------|
| Format | `ruff format services/ packages/ tests/` | ✅ PASS (84 files, 0 reformatted) |
| Lint | `ruff check services/ packages/ tests/` | ✅ PASS (0 errors) |
| Types | `mypy services/ packages/ tests/` | ✅ PASS (0 issues, 84 source files) |
| Tests | `pytest -v` | ✅ PASS (824/824 in 4.31s) |
| Secret scan | `pytest tests/test_secret_scan.py -v` | ✅ PASS (0 findings) |

### Frontend Gates

| Gate | Command | Result |
|------|---------|--------|
| Types | `npx tsc --noEmit` | ✅ PASS (0 errors) |
| Lint | `npm run lint` | ✅ PASS (0 errors, 7 react-refresh warnings) |
| Tests | `npm test -- --run` | ✅ PASS (91/91, 7 test files) |

## Bug Fixes Applied

### 1. Pydantic positional args in test code
**Root cause**: `IncidentCreateRequest("t1", ...)` used positional args; Pydantic v2 `BaseModel.__init__` does not accept positional arguments.
**Fix**: Converted all 3 test call sites to keyword arguments.
**Files**: `tests/test_client_contracts.py` (lines 345, 354, 376)

### 2. Mypy no-any-return in `_should_deliver`
**Root cause**: `getattr(prefs, pref_field)` returns `Any`; mypy --strict flags returning `Any` from a `bool`-typed function.
**Fix**: Wrapped in `bool()`: `return bool(getattr(prefs, pref_field))`
**Files**: `services/client/__init__.py` (line 548)

### 3. Unused imports in app.py
**Root cause**: `IncidentSeverity`, `NotificationPriority`, `NotificationType` imported but not used after the PLR0913 refactor extracted them into Pydantic request models.
**Fix**: `ruff check --fix` removed the unused imports.
**Files**: `services/core/app.py`

### 4. window.matchMedia not available in jsdom
**Root cause**: `isPWA()` calls `window.matchMedia()` which jsdom does not implement; caused 4 vitest failures.
**Fix**: (a) Added `matchMedia` mock to `tests/setup.ts`, (b) added `typeof window.matchMedia === "function"` guard in `isPWA()`.
**Files**: `apps/web/tests/setup.ts`, `apps/web/src/client-contracts.ts`

### 5. Multiple elements matching getByText("SIMULATION")
**Root cause**: The App renders "SIMULATION" in both the header badge and the operating-mode status card; `getByText` throws on multiple matches.
**Fix**: Changed to `getAllByText("SIMULATION").length > 0`.
**Files**: `apps/web/tests/App.test.tsx`

## Changed Files

### Modified
- `apps/web/index.html` — PWA meta tags
- `apps/web/src/App.tsx` — Phase 08 dashboard views, navigation
- `apps/web/src/index.css` — Phase 08 responsive styles
- `apps/web/src/client-contracts.ts` — isPWA() matchMedia guard
- `apps/web/tests/App.test.tsx` — getAllByText fix
- `apps/web/tests/setup.ts` — matchMedia mock for jsdom
- `pyproject.toml` — services.client package registration
- `services/core/app.py` — Phase 08 API endpoints (unused imports removed)
- `services/client/__init__.py` — bool() wrapper for mypy

### New
- `apps/macbook/src-tauri/` — Tauri MacBook app (tauri.conf.json, Cargo.toml, src/*.rs)
- `apps/web/public/manifest.json` — PWA manifest
- `apps/web/src/{remote-commands,notifications,client-contracts,navigation}.ts`
- `apps/web/src/views/*.tsx` — 11 dashboard view components
- `apps/web/tests/{remote-commands,notifications,client-contracts,navigation}.test.ts`
- `services/client/__init__.py` — RemoteCommandService, NotificationService, IncidentService, OnboardingStep, run_simulated_workflow
- `tests/test_client_contracts.py` — ~40 Python tests for Phase 08 contracts

## Security Findings

- **F-SEC-01** (carried): Repo is PUBLIC — should be PRIVATE per Addendum A14. Owner decided to keep public; preserved.
- No secrets detected in source files (secret scan: 0 findings).
- Withdrawal prohibition (AD-019) enforced in ConnectedAccounts view.
- Remote commands require step-up authentication for high-risk operations (AD-027).
- Critical incidents require human approval (AD-017).

## Known Limitations

- Tauri app is configured but not compiled (requires Rust toolchain + native build; configuration verified).
- PWA manifest and meta tags present; full service-worker offline support deferred to Phase 09/10.
- All client interfaces are monitoring/configuration only — not financial execution authorities (Section 03.1).
- In-memory storage (same as prior phases); PostgreSQL persistence planned for Phase 09.

## Acceptance Criteria

Per DIRECTIV.txt Phase 08: "User journeys, authorization, remote commands, and state presentation tests pass."

- ✅ User journey tests pass (onboarding, simulated workflow)
- ✅ Authorization tests pass (step-up for high-risk commands, tenant isolation)
- ✅ Remote command tests pass (idempotency, expiry, step-up, history)
- ✅ State presentation tests pass (notification preferences, incident status, all dashboards)
- ✅ 824/824 pytest, 91/91 vitest, all quality gates clean
