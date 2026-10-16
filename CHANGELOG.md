# CHANGELOG — Kian Trading Intelligence

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with prerelease identifiers during development.

---

## [0.20.0] — Phase D: Final Truth Reset and Status Update

### Changed — Phase D: Final Truth Reset and Status Update
- `status.yaml` — Phase_D added as COMPLETE; "Last updated" header updated to Phase D; directive lineage V1.3 marked superseded, V1.4 active
- `README.md` — Directive badge V1.3 → V1.4; directive version line V1.3 → V1.4; Post-E10 Elevation Phases (A–D) table added; Technology Stack: PostgreSQL and Redis changed PLANNED → REAL; Deployment updated to reflect Render configured as target; governance lineage table updated (V1.3 superseded, V1.4 active); all directive references V1.3 → V1.4
- `docs/architecture.md` — Deployment line updated: "Render planned" → "Render — configured as target, not yet deployed"
- `DIRECTIV.txt` — Replaced with the two-line reserved file (per Phase D acceptance criteria)

### Added — Phase D
- `test-house/phase-d/evidence.md` — Phase D evidence record (scan results, pricing-value assessment)

### Pricing-Value Assessment
- Current pricing: TIER_1 $49/mo, TIER_2 $99/mo, TIER_3 $149/mo (annual: $39/$79/$119)
- Old pricing ($200/$350/$500) was replaced in residual task 02.2 per Section 01.7
- No automatic price change in Phase D; owner decides future pricing
- Assessment: Current pricing is competitive for a simulation-grade multi-tenant trading intelligence platform with per-tenant budget governance, decision replay, signed risk tokens, and real PostgreSQL/Redis infrastructure

### Invariants enforced (non-negotiable)
- All public files consistent with actual implemented state after Phases A–C
- No stale references to old pricing (200/350/500) as current values
- `status.yaml` remains the single source of truth
- `live_authorized` remains false; `operating_mode` remains SIMULATION

---

## [0.20.0] — Post-E10 Residual Task 02.4: Final README and Status Truth Reset

### Changed — Post-E10 Residual Task 02.4
- `status.yaml` — E0 status changed IN_PROGRESS → COMPLETE; E1–E7 status changed PLANNED → COMPLETE; acceptance criteria updated; test count updated 1789 → 1906; "Last updated" header updated to reflect residual task 02.4
- `README.md` — Elevation Phase Status table updated: E0–E7 now show ✅ COMPLETE (were IN PROGRESS/PLANNED); phase badge updated from "E9 Graduated Autonomy" to "E0–E10 COMPLETE"; DIRECTIV.txt reference corrected from V1.2 to V1.3
- `tests/test_e0_consistency.py` — `test_e0_in_progress` renamed to `test_e0_complete` and updated to assert E0 is COMPLETE; docstring updated to reflect that E0–E10 may all be COMPLETE

### Invariants enforced (non-negotiable)
- E0–E10 all show COMPLETE consistently across `status.yaml`, `README.md`, and `CHANGELOG.md`
- `live_authorized` remains false; `operating_mode` remains SIMULATION
- No residual discrepancies between status.yaml, README, and CHANGELOG

---

## [0.20.0] — Post-E10 Residual Task 02.2: Owner Decisions from Section 01

### Added — Post-E10 Residual Task 02.2
- `packages/contracts/platform_config.py` — platform infrastructure configuration implementing all "Current (now)" owner decisions from DIRECTIV.txt Section 01:
  - `CloudProvider` enum: RENDER (current), AWS (roadmap)
  - `EventBusProvider` enum: REDIS_STREAMS (current), AWS_SQS_SNS (roadmap)
  - `SLOTargets` dataclass: 99.0% / ≤15min RPO / ≤60min RTO (current), 99.9% / ≤1min / ≤15min (roadmap)
  - `ExchangeProviderName` enum and `ExchangeProviderConfig`: Kraken + Bitvavo (current, MiCA-licensed); Binance + Bybit + OKX + Coinbase (roadmap)
  - `LegalClassificationConfig`: EU/German MiCA/GDPR templates (current), no counsel engaged, live not authorized
  - `NotificationProviderConfig`: SendGrid email (current); Slack + Twilio SMS (roadmap with dual-control)
  - `PlatformConfig` aggregate: all current decisions collected; `live_trading_authorized` invariant always False
- `tests/test_02_2_owner_decisions.py` — 44 tests covering all Section 01 owner decisions

### Changed — Post-E10 Residual Task 02.2
- `packages/contracts/billing.py` — pricing updated per Section 01.7 (Pricing Tiers adjusted):
  - TIER_1: $200/mo → $49/mo; annual $39/mo
  - TIER_2: $350/mo → $99/mo; annual $79/mo
  - TIER_3: $500/mo → $149/mo; annual $119/mo
  - `TIER_ANNUAL_MONTHLY_USD` dict added for explicit annual pricing
  - `ANNUAL_DISCOUNT_RATE` updated from 0.1667 to 0.2041 (derived from new pricing)
- `services/billing/__init__.py` — `build_plan()` now uses explicit annual monthly prices from Section 01.7 instead of deriving from discount rate
- `tests/test_e10_billing.py` — all price assertions updated to match new pricing
- `status.yaml` — directive_version 1.2 → 1.3; V1.3 added to lineage; OPEN-02/03/05/06/08/09 marked RESOLVED with owner decisions; E0 branch updated; E10 marked COMPLETE in README
- `services/core/version.py` — version 0.19.0 → 0.20.0
- `pyproject.toml` — version 0.19.0 → 0.20.0
- `README.md` — directive version V1.2 → V1.3; software version 0.10.0 → 0.20.0; E10 status PLANNED → COMPLETE; governance lineage table updated
- `tests/test_e0_consistency.py` — `test_directiv_is_v1_2` and `test_directive_version_consistency` updated to accept V1.3

### Invariants enforced (non-negotiable)
- `live_trading_authorized` is ALWAYS False in `PlatformConfig`, `ExchangeProviderConfig`, and `LegalClassificationConfig`
- No current exchange provider is `is_live_authorized`
- Current legal classification requires SIMULATION/PAPER only until formal legal review
- Safety controls (Risk Kernel, kill plane, audit) are NEVER gated by any TierFeature or payment tier

---

## [0.19.0] — E10: Commercial Monetization, Payment Tiers and Market Readiness

### Added — E10: Commercial Monetization, Payment Tiers and Market Readiness
- `packages/contracts/billing.py` — complete commercial billing contract layer per AD-034:
  - `SubscriptionTier` enum: FREE_TRIAL (1-week), TIER_1 ($49/mo), TIER_2 ($99/mo), TIER_3 ($149/mo)
  - `BillingPeriod` enum: MONTHLY and ANNUAL (with owner-approved discount rate, OD-7)
  - `SubscriptionStatus` lifecycle enum (TRIALING → ACTIVE → PAST_DUE → CANCELLED / EXPIRED / SUSPENDED)
  - `MeteringDimension` enum: ORDERS, LLM_TOKENS, MARKET_DATA, COMPUTE_SEC
  - `BillingEventType` enum: 17 auditable billing lifecycle event types
  - `OnboardingStep` enum: commercial onboarding funnel steps
  - `TierFeature` enum: feature flags gated by tier (safety invariants never gated)
  - `TIER_FEATURE_MAP` — immutable tier → feature set mapping; `tier_has_feature()` helper
  - `TIER_USAGE_LIMITS` — per-tier usage limits; TIER_3 unlimited for all dimensions
  - `SubscriptionPlan` — immutable plan with pricing invariants (FREE_TRIAL always $0)
  - `TenantSubscription` — mutable subscription record with lifecycle fields
  - `UsageRecord` — frozen metered usage event (quantity > 0 invariant)
  - `UsageSummary` — aggregated usage with warning/exceeded dimension lists
  - `BillingEvent` — frozen, SHA-256 hash-signed auditable billing event
  - `OnboardingRecord` — append-only onboarding funnel record with required-step tracking
  - `TierMetrics` / `UnitEconomicsDashboard` — unit-economics snapshot contracts with snapshot_hash
  - `MarketReadinessGate` / `GateResult` / `MarketReadinessReport` — Section 23 gate contracts; `live_trading_authorized` invariant always False; `owner_sign_off_required` invariant always True
  - `ApplePlatformDecision` — OD-8 Apple Developer Program decision record; `pwa_path_requires_apple_license` invariant always False
  - `FeatureNotAvailableError`, `UsageLimitExceededError`, `SubscriptionNotFoundError` — domain exceptions
- `services/billing/__init__.py` — billing, tier enforcement and onboarding services:
  - `build_plan()` — constructs `SubscriptionPlan` with correct monthly/annual pricing
  - `BillingEventLog` — append-only, SHA-256 hash-chain-verified billing event log; `verify_chain()` detects any tampering
  - `UsageMeteringService` — accurate, auditable usage recording; 80% warning events; hard limit enforcement (never weakens safety); unlimited TIER_3 support
  - `BillingService` — subscription lifecycle (start_trial, subscribe, cancel, expire_trial, renew); feature gating via `check_feature()` (safety invariants never routed here)
  - `OnboardingService` — idempotent onboarding step completion; `ONBOARDING_COMPLETED` event on funnel completion
  - `build_market_readiness_report()` — evaluates all Section 23 gates and produces signed `MarketReadinessReport`
- `services/billing/unit_economics.py` — `UnitEconomicsService`: produces hashed `UnitEconomicsDashboard` snapshots with MRR, ARR, tier breakdowns, trial conversions, churn; retains snapshot history for audit
- `tests/test_e10_billing.py` — 80 tests covering all billing/tier/metering/onboarding/market-readiness scenarios
- `test-house/phase-e10/evidence.md` — phase evidence record

### Changed — E10: Commercial Monetization, Payment Tiers and Market Readiness
- `pyproject.toml` — version bumped to 0.19.0; `services.billing` package registered
- `services/core/version.py` — `__version__` synchronized to 0.19.0
- `status.yaml` — E10 COMPLETE; `commercial_billing`, `payment_tiers`, `usage_metering` honest labels changed PLANNED → REAL; test count updated to 1789; software_version header updated
- `tests/test_e0_consistency.py` — `test_e1_through_e10_planned` renamed and updated to `test_e1_through_e10_exist_with_known_status` to correctly reflect that phases may be PLANNED, IN_PROGRESS, or COMPLETE as elevation progresses

### Invariants enforced (non-negotiable, per AD-034 and Section 00.4)
- `live_trading_authorized` is ALWAYS False in `MarketReadinessReport` and `E9OwnerReviewPackage`
- `owner_sign_off_required` is ALWAYS True in `MarketReadinessReport`
- `pwa_path_requires_apple_license` is ALWAYS False in `ApplePlatformDecision`
- Safety features (Risk Kernel, kill plane, audit) are NEVER gated by `TierFeature`
- Usage limits are enforced as domain exceptions — they NEVER affect safety controls

---

## [Unreleased] — E0: Truth Reset and Governance Repair

### Added — E0: Truth Reset and Governance Repair
- `status.yaml` — single source of truth for project status, phase progress, security findings, test counts, and honest labeling (REAL vs PLANNED)
- `docs/adr/` directory with ADR templates for open engineering decisions (OPEN-02, OPEN-03, OPEN-05, OPEN-06, OPEN-08, OPEN-09)
- `docs/adr/README.md` — ADR index, template, and governance precedence documentation
- Directive lineage documentation (V1.0 → V1.1 → V1.2) in `status.yaml` and README
- Repository visibility decision documented (PUBLIC — owner-decided per Addendum A14, F-SEC-01)
- Honest REAL/SIMULATED/PLANNED labeling applied to all public claims in README and status.yaml
- CI consistency check test (`tests/test_e0_consistency.py`) verifying every public claim links to evidence or is labeled PLANNED
- `DIRECTIV.txt` updated to V1.2 (Elevation and Market Completion) — AD-034 through AD-040, E0 through E10

### Changed — E0: Truth Reset and Governance Repair
- `README.md` rewritten with honest status: elevation phase table (E0–E10), prior phase table (01–10), security findings table, REAL/PLANNED labeling per technology, directive lineage table
- `CHANGELOG.md` reconstructed with all prior phases (01–10) and F-SEC-02/03 remediation
- `docs/architecture.md` updated with AD-034 through AD-040 summary
- `pyproject.toml` version synchronized to 0.10.0 (matching `services/core/app.py`)

### Fixed — E0: Truth Reset and Governance Repair
- Truth drift: README previously claimed "Phase 09 IN PROGRESS" and "Phase 10 PLANNED" — all prior phases 01–10 are COMPLETE (merged to main)
- Truth drift: README previously listed F-SEC-02/03 as "unresolved release blockers" — both are RESOLVED (merged, PR #12)
- Version inconsistency: `pyproject.toml` was 0.1.0 while `services/core/app.py` was 0.10.0 — synchronized to 0.10.0

---

## [0.10.0] — Prior Phases 01–10 + Security Remediation

### Added — Phase 01: Repository & Engineering Foundation
- Repository identity and remote verification (GitHub: aminbita162-glitch/kian-trading-intelligence)
- Structured monorepo layout (`apps/`, `services/`, `agents/`, `packages/`, `infrastructure/`, `tests/`, `docs/`, `test-house/`)
- Python 3.11+ / FastAPI backend foundation with health endpoint and OpenAPI documentation
- TypeScript 5.6+ / React / Vite frontend foundation with strict type checking
- Shared contracts package (`packages/contracts/`) with Pydantic models for operating modes and order states
- Dependency management with `pyproject.toml` (backend) and `package.json` (frontend)
- Code formatting and linting: Ruff (Python), ESLint + Prettier (TypeScript)
- Unit-test framework: pytest (Python) with passing baseline tests, Vitest (TypeScript)
- CI configuration via GitHub Actions (`.github/workflows/ci.yml`)
- Secret-handling rules: `.gitignore` exclusions, environment file patterns, no-secrets policy
- Architecture documentation (`docs/architecture.md`)
- Proprietary LICENSE file (pending owner/legal review)
- Test house evidence library (`test-house/`) with structured phase directories
- Engineering integrity policy in README.md

### Added — Phase 02: Identity & Multi-Tenant Security
- Tenant and user models with multi-tenant isolation (AD-002, AD-008, AD-010)
- Authentication with account lockout tracking (AD-010, AD-026)
- Authorization policies and step-up authentication (AD-026)
- Profile management and risk policy configuration (AD-008)
- MFA support (TOTP) with enable/verify flow (AD-026)
- Session management with expiry and revocation (AD-026)
- Credential vault with encryption and rotation (AD-019)
- Tenant isolation in all data access paths (AD-002)
- Audit event recording (AD-022)
- Database migrations (SQLite dev / PostgreSQL prod)
- Adversarial access-control tests
- 127/127 pytest, 29/29 vitest, all gates clean

### Added — Phase 03: Market Data Foundation
- Market data contracts (`Symbol`, `Timeframe`, `Ticker`, `OrderBook`, `Candle`)
- Simulated market data provider with deterministic data generation (AD-003)
- Provider adapter interfaces with normalized event schema (AD-005, AD-021)
- Normalized market events and timestamp/freshness checks (AD-021)
- Duplicate handling and sequence tracking
- Historical storage with replay engine
- Deterministic indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
- Rate-limit handling and reconnection behavior (AD-021)
- 245/245 pytest (127 existing + 118 new), 29/29 vitest, all gates clean

### Added — Phase 04: Risk Kernel & Trading Execution
- Risk kernel contracts (`RiskAssessment`, `RiskPolicy`, `ExposureExceededError`)
- Risk kernel service with deterministic safety validation (AD-004, AD-013)
- Trading session contracts (10 states, legal transitions, AD-014)
- Exchange simulator with deterministic fill simulation (AD-023)
- Execution engine with order lifecycle management (AD-014, AD-020)
- Concurrency tests verifying thread-safe exposure tracking (AD-013)
- Concentration limit and emergency-stop enforcement (AD-013)
- 370/370 pytest (245 existing + 125 new), 29/29 vitest, all gates clean

### Added — Phase 05: Financial Ledger & Profit Policies
- Financial account model with multi-asset support (AD-007, AD-018)
- Balanced double-entry journal with value-based balancing (AD-018)
- Fill-to-ledger mapping with realized P&L calculation (AD-007)
- Decimal precision throughout financial calculations (AD-018)
- Fee accounting and unrealized P&L tracking
- Profit thresholds and profit reservation contracts (AD-007)
- Reconciliation service with deadlock-safe balance access
- Withdrawal-request contracts with withdrawal prohibition (AD-019)
- Financial invariant tests (balance, precision, idempotent posting)
- 524/524 pytest (370 existing + 154 new), 29/29 vitest, all gates clean

### Added — Phase 06: Four-Agent Intelligence
- Four agent contracts (Market Intelligence, Strategy & Portfolio, Execution & Supervisor, Mining Operations) (AD-004)
- Agent permission boundaries with frozenset validation (AD-020)
- Deterministic orchestration with agent context and permission checks (AD-020)
- Strategy versioning with state transitions (DRAFT → BACKTESTING → OUT_OF_SAMPLE → WALK_FORWARD → PAPER_TRADING → VALIDATED)
- Backtesting, out-of-sample, walk-forward, and paper trading validation (AD-012)
- Validated ML interfaces and LLM gateway with token budgets (AD-011, AD-025)
- Decision traceability with `DecisionTrace` records (AD-022)
- 631/631 pytest (524 existing + 107 new), 29/29 vitest, all gates clean

### Added — Phase 07: Mining Simulation & Safety
- Mining simulator with hash-rate and reward models (AD-015)
- Electricity cost and depreciation calculations
- Pool interface contracts (simulation)
- Hardware telemetry simulation
- Temperature policies and failure simulation
- Mining financial integration with ledger (AD-007)
- Controlled adapter interfaces (AD-015)
- 769/769 pytest (631 existing + 138 new), 29/29 vitest, all gates clean

### Added — Phase 08: MacBook & iPhone Applications
- Tauri MacBook application shell (`apps/macbook/src-tauri/`) with `tauri.conf.json`, `Cargo.toml`, Rust entry points
- Responsive iPhone PWA (`apps/web/public/manifest.json`, PWA meta tags in `index.html`)
- Onboarding flow with 8-step wizard (`OnboardingStep` enum)
- Trading, mining, and financial dashboard views
- Calendar scheduler view for trading session scheduling
- Secure remote command service (AD-027) with step-up authentication, idempotency, and expiry
- Notification hub (AD-009) with `NotificationCreateRequest`, preferences, and priority levels
- Connected-account settings with withdrawal prohibition (AD-0019)
- Incident and recovery interface (AD-017) with severity levels and human-approval gate
- End-to-end simulated workflow (`run_simulated_workflow`)
- 11 dashboard view components in `apps/web/src/views/`
- 824/824 pytest, 91/91 vitest, all gates clean

### Added — Phase 09: Security, Resilience, and Scale
- Threat-model review with `ThreatFinding`, `ThreatModelReport`, `SecurityService` (AD-010, AD-022)
- Security scanning with `ScanResult`, `ScanType` (static, dependency, secret, infrastructure, license)
- Tenant-isolation testing — cross-tenant access denied (AD-002, AD-010)
- Risk stress tests — exposure, daily-loss, concentration, emergency-stop, concurrent authorization (AD-013)
- Financial stress tests — double-entry balance, decimal precision, idempotent posting (AD-018)
- Backup restoration with SHA-256 checksums and integrity verification (AD-028)
- Disaster recovery — 5-phase state machine, human authorization mandatory (AD-017, AD-028)
- Split-brain simulation — leader/follower roles, quorum detection (AD-016, AD-028)
- Fault injection — 6 fault types (network, latency, crash, disk-full, corruption, timeout) (AD-023)
- Load testing — p50/p95/p99 latency, throughput, error rate (AD-016)
- Observability verification — structured logs, traces, metrics, SLO compliance (AD-022)
- Cost and token evaluation — per-request cost, deterministic-first ratio (AD-025)
- 933/933 pytest (824 existing + 109 new), 91/91 vitest, all gates clean

### Added — Phase 10: Release Engineering and Controlled Launch
- Final architecture review with 5 gates (AD-033)
- Dependency verification — 8 pinned standard dependencies (AD-024)
- Release artifact integrity — SHA-256 checksums, 6 artifact types (AD-024)
- Migration verification — applied/reversible/rollback-tested tracking (AD-024)
- Staging deployment with health checks (AD-024)
- Shadow/canary readiness — 5-stage, auto-abort on bad metrics (AD-024)
- Rollback testing — data integrity + financial-effects-preserved (AD-024)
- 8 operational runbooks — all with human-approval gates (AD-017, AD-028)
- User documentation — 3 guides (AD-030)
- Administrator documentation — 3 guides + API reference + compliance (AD-022)
- Release evidence package — 9 mandatory evidence types (AD-032)
- Final readiness report — GO/NO_GO/CONDITIONAL_GO, never sets `live_authorized` (AD-033)
- 1071/1071 pytest (933 existing + 138 new), 91/91 vitest, all gates clean

### Security — F-SEC-02/03 Remediation
- F-SEC-02 RESOLVED: Credential vault upgraded from XOR to AES-256-GCM envelope encryption
  with AAD binding, key versioning, fail-closed production, and legacy XOR migration.
  Tests: `tests/test_f_sec_02_encryption.py`. Evidence: `test-house/security/f-sec-02-03-evidence.md`
- F-SEC-03 RESOLVED: Identity store upgraded from in-memory to SQLAlchemy-backed
  `PersistentIdentityStore` with SQLite (dev) / PostgreSQL (prod), versioned migrations,
  persistent password hashing, and fail-closed production. Python 3.13 ResourceWarning
  resolved via `close()` method + instance tracking + `conftest.py` autouse fixture.
  Tests: `tests/test_f_sec_03_persistence.py`. Evidence: `test-house/security/f-sec-02-03-evidence.md`
- 1121/1121 pytest (1071 existing + 50 security tests), 91/91 vitest, all gates clean
- Merged to main via PR #12 (commit 87759bd), CI all-green (Python 3.11/3.12/3.13 + Frontend)

### Security
- No secrets, credentials, or API keys committed to the repository
- `.gitignore` configured to prevent accidental secret commits
- Repository visibility: PUBLIC (owner-decided per Addendum A14 — F-SEC-01 recorded, not a blocker)
- Critical threat-model findings block release (`has_blocking_findings`)
- Disaster recovery requires human authorization before resumption (AD-017)
- Backup restoration verifies SHA-256 checksums (AD-028)
- `generate_report()` never sets `live_authorized` — verified by test
- No live trading, real mining, or real financial operations are enabled or authorized at this stage

---

## [0.1.0-dev] — Initial scaffold

Prerelease identifier. Initial engineering foundation established in Phase 01.

---

## Attribution

**Amin Azimi | AI Architect | End-to-End System Development Business Challenge | Azimi Innovation Lab**
